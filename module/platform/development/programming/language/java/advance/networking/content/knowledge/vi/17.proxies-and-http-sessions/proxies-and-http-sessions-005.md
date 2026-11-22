# Authenticator và PasswordAuthentication cho máy chủ hoặc proxy trong Java 17

Trong phần **Proxy và phiên HTTP** của Java Advanced Networking, một HTTP client có thể bị **máy chủ đích (origin server)** hoặc **proxy trung gian** yêu cầu xác thực trước khi trả dữ liệu. Java cung cấp cặp API **java.net.Authenticator** và **java.net.PasswordAuthentication** để ứng dụng trả về tên đăng nhập/mật khẩu khi tầng networking gặp một yêu cầu xác thực phù hợp. Với **java.net.http.HttpClient** từ Java 11 trở lên, bạn gắn một Authenticator vào **HttpClient.Builder.authenticator(...)**, sau đó HttpClient có thể hỏi credentials khi xử lý challenge HTTP mà nó hỗ trợ.

**Điểm phân biệt quan trọng nhất:** Authenticator trong bài này là **đối tượng phía client cung cấp credentials cho server hoặc proxy**, chứ **không** phải bộ xác thực người dùng đăng nhập **vào chính HTTP server của bạn**. Nếu đang xây một Java HTTP server tiếp nhận request, phần kiểm tra Authorization từ client là trách nhiệm của server framework/gateway hoặc server-side security filter. Hai chiều này không thể thay thế cho nhau.

Bài học sẽ giải thích:

- Khi nào origin server dùng **401 Unauthorized** với **WWW-Authenticate**, còn proxy dùng **407 Proxy Authentication Required** với **Proxy-Authenticate**.
- Vì sao **Authorization** và **Proxy-Authorization** phải được gửi đúng bên nhận; vì sao không thể chuyển credentials của proxy sang origin.
- Cách override **Authenticator.getPasswordAuthentication()**, dùng **getRequestorType()**, **getRequestingHost()**, **getRequestingPort()**, **getRequestingScheme()** và các trường ngữ cảnh để **chỉ phát credentials tới nơi được phép**.
- Cách dùng **PasswordAuthentication(String, char[])**, hiểu vòng đời char[] và bảo vệ secrets.
- Cách cấu hình **HttpClient.Builder.authenticator** và **ProxySelector** đúng cho Java 17, kể cả các giới hạn HTTP Basic, HTTPS, proxy CONNECT, authentication cache và retry.
- Hai chương trình Java 17 hoàn chỉnh chạy trên loopback: chương trình có cả **origin 401** và **mock HTTP proxy 407**, chương trình còn lại kiểm thử allowlist credentials mà không tạo network request.
- Cạm bẫy bảo mật, lỗi thường gặp, kiểm thử âm, bài tập và câu hỏi ôn luyện.

Môi trường thực hành giả lập **HTTP Basic authentication trên 127.0.0.1** bằng credentials cố định **student/lab-only**. Đây **chỉ là dữ liệu giả trong lab**, tuyệt đối không dùng HTTP Basic qua mạng ngoài mà thiếu cơ chế bảo vệ phù hợp.

## 1. Phân biệt origin server và HTTP proxy

Giả sử ứng dụng Java gửi GET tới một web API:

~~~text
Java HttpClient
      |
      | HTTP request
      v
Origin server: api.example.org
~~~

Nếu origin cần xác thực HTTP, nó có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
~~~

Client có thể hỏi Authenticator để lấy username/password thích hợp rồi gửi request khác có header:

~~~http
Authorization: Basic <credentials-encoded>
~~~

**Basic** mã hóa chuỗi username:password bằng Base64 cho cách truyền trong header; **Base64 không phải mã hóa bảo mật**. Khi dùng mạng thật, phải có kênh TLS đáng tin cậy và kiểm tra đúng server certificate/hostname. Không ghi ra log header Authorization và không đưa password thật trong code.

Nếu ứng dụng phải đi qua **forward proxy**:

~~~text
Java HttpClient
      |
      | (1) gửi request tới proxy
      v
Corporate proxy: proxy.internal:8080
      |
      | (2) proxy chuyển tiếp tới origin nếu được phép
      v
Origin server: api.example.org
~~~

Chính proxy có thể yêu cầu người gọi xác thực:

~~~http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Basic realm="company-proxy"
~~~

Khi đáp ứng challenge của proxy, credentials dành cho **proxy**, đi trong:

~~~http
Proxy-Authorization: Basic <proxy-credentials-encoded>
~~~

**Không tự đổi 401 thành 407 hoặc ngược lại.** Hai mã này thuộc **hai chủ thể xác thực khác nhau** và ứng dụng có thể cần hai bộ credentials với phạm vi tin cậy riêng.

| Thuộc tính | Origin server authentication | Proxy authentication |
|---|---|---|
| Bên yêu cầu | Máy chủ tài nguyên cuối | Forward proxy |
| HTTP status challenge | **401** | **407** |
| Header challenge phản hồi | **WWW-Authenticate** | **Proxy-Authenticate** |
| Header credential trong request | **Authorization** | **Proxy-Authorization** |
| Authenticator.RequestorType | **SERVER** | **PROXY** |
| Host/port cần dùng để quyết định cấp mật khẩu | Host/port của origin đã được phê duyệt | Host/port của proxy đã được phê duyệt |
| Chứng minh quyền truy cập dữ liệu nghiệp vụ? | Không tự động; server vẫn kiểm tra authorization | Không; chỉ xác thực được với proxy |
| Có thể xảy ra đồng thời? | Có | Có; dùng credentials tách biệt |

**Một request có thể gặp cả hai challenge:** proxy yêu cầu credentials trước để chuyển tiếp, sau đó origin server yêu cầu credentials khác. Đừng dùng một cặp user/password chung cho cả hai chỉ vì đều gọi **Authenticator**.

## 2. Authenticator thực sự làm gì?

**java.net.Authenticator** là lớp cho phép networking code hỏi ứng dụng về **PasswordAuthentication** trong ngữ cảnh xác thực hiện tại. Cách thường dùng là tạo lớp con và override:

~~~java
Authenticator auth = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        // Kiểm tra ngữ cảnh đang yêu cầu xác thực.
        // Nếu không thuộc phạm vi cho phép: return null.
        // Nếu hợp lệ: return new PasswordAuthentication(user, passChars);
        return null;
    }
};
~~~

Đây chỉ là **mẫu cấu trúc**, chưa phải chương trình runnable. Một Authenticator mặc định không cung cấp thông tin đăng nhập; **getPasswordAuthentication() mặc định trả null**.

HttpClient sử dụng callback này khi một phản hồi HTTP yêu cầu xác thực bằng scheme mà JDK/provider hỗ trợ. **Không nên giả định callback được gọi đúng một lần cho mỗi HttpRequest**: authentication có thể chịu ảnh hưởng của challenge, caching, connection reuse, HTTP version, redirect, proxy và implementation. Cũng không nên coi Authenticator như một hook gọi trước **mọi** request.

### Các phương thức protected cung cấp ngữ cảnh

| Method | Giá trị/ngữ nghĩa |
|---|---|
| **getRequestorType()** | **Authenticator.RequestorType.SERVER** hay **PROXY** |
| **getRequestingHost()** | Hostname của bên đang yêu cầu; có thể null |
| **getRequestingPort()** | Port của kết nối đang yêu cầu xác thực |
| **getRequestingSite()** | InetAddress nếu được biết; có thể null |
| **getRequestingProtocol()** | Protocol, ví dụ **http** hoặc **https** |
| **getRequestingScheme()** | Scheme xác thực HTTP như **Basic**, tùy challenge/provider |
| **getRequestingPrompt()** | Prompt/realm từ yêu cầu xác thực (nếu có) |
| **getRequestingURL()** | URL liên quan tới yêu cầu, có thể null tùy nguồn |
| **getPasswordAuthentication()** | Trả credentials hoặc **null** để từ chối |

**getRequestingScheme() không đồng nghĩa URI scheme.** Ví dụ "Basic" là **HTTP authentication scheme**, còn "https" là **protocol/URI scheme**. Lẫn hai khái niệm này có thể khiến bạn cấp credentials sai trường hợp.

### RequestorType là ranh giới bảo mật

Một Authenticator chia sẻ có thể nhận yêu cầu từ nhiều nơi. Nếu viết:

~~~java
@Override
protected PasswordAuthentication getPasswordAuthentication() {
    return new PasswordAuthentication("admin", secret);
}
~~~

thì ứng dụng có nguy cơ **cấp cùng credentials cho mọi nơi Authenticator được hỏi**, kể cả proxy hoặc host khác, nếu không có chính sách kiểm tra. Đây là **anti-pattern**. Trong production, phải xác minh ít nhất **RequestorType + host + port + auth scheme + trust policy/realm theo nghiệp vụ** trước khi trả secrets.

**Không phụ thuộc vào một Host header tùy ý** để quyết định gửi mật khẩu. Host/port dùng trong Authenticator context do networking stack tạo, nhưng việc định danh host vẫn phải được kiểm tra với chính sách endpoint/proxy của ứng dụng; nếu cho người dùng tự cung cấp URL hoặc ProxySelector, phải chống SSRF/redirect và kiểm soát endpoint.

### Chấp nhận hay từ chối

- Khi policy **khớp** và secret hợp lệ, trả **PasswordAuthentication**.
- Khi type/host/port/scheme/realm/URL không thuộc phạm vi đã phê duyệt, **trả null**, không cấp mật khẩu.
- Khi secrets manager lỗi hoặc secret hết hạn, báo lỗi ứng dụng, không fallback sang credentials rộng hơn.
- Không trả sai user/password liên tục để kích hoạt nhiều vòng challenge/retry. Đặt deadline, số lần thử và quan sát lỗi theo policy.

## 3. PasswordAuthentication lưu gì và không lưu gì?

**java.net.PasswordAuthentication** là một **data holder** đơn giản:

~~~java
PasswordAuthentication credentials =
        new PasswordAuthentication("service-user", passwordChars);

String username = credentials.getUserName();
char[] password = credentials.getPassword();
~~~

Đây là đoạn minh họa, với **passwordChars** đã được nạp từ nơi an toàn. Nó **không** tự thực hiện login, gửi HTTP request, lưu cookie, chọn proxy, mã hóa TLS hay kiểm tra quyền ở server.

Constructor nhận **String userName** và **char[] password**. Theo Javadoc, **constructor sao chép mảng password đầu vào** trước khi lưu. **getPassword() trả về tham chiếu tới mảng password đang được đối tượng giữ**, vì vậy caller có trách nhiệm xử lý an toàn và xóa nội dung mảng khi không còn dùng. Không giả định mật khẩu sẽ tự biến mất khỏi bộ nhớ ngay khi object không còn được tham chiếu.

### Tại sao dùng char[] thay cho String?

**String là immutable**; ứng dụng không thể xóa từng ký tự trong một String nhạy cảm đã được tạo. Với **char[]**, khi thực sự sở hữu mảng, có thể dùng **Arrays.fill(secret, '\0')** trong finally sau khi sử dụng xong. Tuy nhiên:

- Mảng có thể đã được copy vào PasswordAuthentication hoặc một thư viện khác; xóa **một mảng** không bảo đảm xóa mọi bản sao.
- Mã thử nghiệm trong bài hardcode "lab-only" và tạo mảng tạm, chỉ nhằm dễ học; điều này **không phù hợp production**.
- Không gọi **new String(secretChars)** để tiện log/debug, vì như thế tạo một bản sao immutable.
- Không giữ char[] trong static fields lâu vô hạn; cần chính sách reload/rotation, time-to-live và hạn chế quyền.
- Tránh đưa username/password vào **URI userinfo** hoặc query string, vì URL có thể bị log, cache, metrics hoặc history ghi lại.
- Không trả PasswordAuthentication cho một host mới chỉ vì nó cũng trả WWW-Authenticate: Basic.

**PasswordAuthentication không phải Authorization header.** HTTP client/provider dùng object và challenge để thiết lập cơ chế xác thực được hỗ trợ; code ứng dụng không nên tự Base64 credentials rồi ghép Authorization khi đã chọn sử dụng Authenticator, trừ khi thực sự kiểm soát đầy đủ chính sách và API headers của phiên bản đang dùng.

## 4. Gắn Authenticator riêng vào Java 17 HttpClient

Java 17 cung cấp **java.net.http.HttpClient.Builder.authenticator(Authenticator)**:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .authenticator(myAuthenticator)
        .build();
~~~

Đây là snippet minh họa; **myAuthenticator** phải là Authenticator đã cấu hình policy/credential provider. **HttpClient** sau khi build là đối tượng bất biến có thể gửi nhiều request; **builder không thread-safe**. Không tạo một HttpClient mới vô điều kiện cho mỗi request nếu muốn tận dụng quản lý connections.

Đối với proxy:

~~~java
HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.example.internal", 8080)))
        .authenticator(myAuthenticator)
        .build();
~~~

Vẫn là snippet, **proxy.example.internal** chỉ là tên minh họa; không gửi request tới nó trong demo. **ProxySelector** chọn đường đi của network request, **Authenticator** quyết định credentials khi có challenge. **Cấu hình một proxy không có nghĩa đã xác thực với proxy**; proxy có thể mở hoặc yêu cầu credentials khác.

### Authenticator ở phạm vi HttpClient hay JVM?

| API | Phạm vi/cách hoạt động |
|---|---|
| **HttpClient.Builder.authenticator(auth)** | Đặt Authenticator **cho HttpClient cụ thể** |
| **HttpClient.authenticator()** | Trả **Optional<Authenticator>** được cấu hình trên client |
| **Authenticator.setDefault(auth)** | Thiết lập **default authenticator cấp JVM** cho networking API sử dụng mặc định |
| **ProxySelector.of(address)** | Chọn một HTTP proxy cho các requests được áp dụng |
| **HttpClient.Builder.NO_PROXY** | Chọn **direct connection**, không đi qua proxy |
| **HttpURLConnection** | API cũ với chính sách/default authenticator và các chi tiết riêng |
| **java.net.http.HttpClient** | Client hiện đại; khi cần auth cụ thể, gắn authenticator trực tiếp trong builder |

**Khuyến nghị thiết kế:** khi làm service nhiều tenants hoặc nhiều endpoints, **tránh Authenticator.setDefault(...)** nếu có thể. Đây là cấu hình toàn tiến trình; thư viện khác cũng có thể hỏi default authenticator và vô tình nhận credentials không dành cho nó. Một **HttpClient per security boundary** với Authenticator scoped thường rõ ràng hơn. Không suy rằng tất cả thư viện đều tuân theo setDefault theo cùng một cách; hãy đọc API cụ thể.

### Authenticator không phải phương án duy nhất cho mọi loại auth

- HTTP **Basic** challenge có thể dùng PasswordAuthentication khi provider hỗ trợ.
- **Digest/NTLM/Kerberos/Negotiate** phụ thuộc thư viện/provider/JDK và chính sách bảo mật; đừng assume mọi scheme có trong header đều được Java 17 HttpClient hỗ trợ.
- **Bearer token (OAuth 2.0/JWT)** thường dùng **Authorization: Bearer ...** có lifecycle/refresh riêng; **PasswordAuthentication** không tự biến username/password thành bearer token.
- **mTLS** dùng SSLContext/certificates, không phải PasswordAuthentication cho HTTP Basic.
- **Cookie/session auth** cần cơ chế CookieHandler/CookieManager hoặc client library, không được thực hiện chỉ bằng getPasswordAuthentication.

## 5. Luồng 401: máy chủ yêu cầu Basic credentials

~~~text
Java HttpClient                                 Origin server
      |                                              |
      | -------- GET /private ---------------------> |
      |                                              |
      | <--- 401 + WWW-Authenticate: Basic --------- |
      |                                              |
HttpClient hỏi Authenticator:
    RequestorType = SERVER
    host/port/scheme/realm...
      |
Authenticator kiểm tra allowlist và trả
PasswordAuthentication(username, char[])
      |
      | -------- GET /private ---------------------> |
      |           Authorization: Basic ...          |
      |                                              |
      | <---------------- 200 OK ------------------- |
      |                                              |
~~~

Sơ đồ cố ý đơn giản hóa. Provider có thể cache trạng thái/challenge, giới hạn số lần thử và xử lý lại request theo implementation. Không giả định luôn có **chính xác hai HTTP requests trên wire** trong mọi điều kiện, dù đây là trường hợp điển hình của Basic challenge ở lần đầu.

**HTTP 401 có thể là kết quả hợp lệ khi không có credentials**, không nhất thiết biến thành IOException. Khi dùng HttpClient, application phải kiểm tra **HttpResponse.statusCode()** và xử lý 401/403 theo chính sách. Nếu credentials được cung cấp nhưng vẫn không hợp lệ, server có thể tiếp tục 401; client có thể ngừng thử sau một giới hạn hoặc báo lỗi tùy implementation.

### Basic authentication không mã hóa password

~~~text
Authorization: Basic base64(username + ":" + password)
~~~

Base64 chỉ là **encoding có thể đảo ngược**, không phải encryption/hash. Dùng **HTTPS** với certificate verification đúng khi gửi credentials đến origin ngoài mạng đáng tin. Không để proxy TLS interception hoặc logging leak credentials. Không ghi Authorization vào logs/traces, và giới hạn nơi credentials có thể được gửi.

## 6. Luồng 407: proxy yêu cầu credentials

~~~text
Java HttpClient                 Forward proxy                Origin
      |                              |                       |
      | ----- GET absolute-URI ----> |                       |
      | <---- 407 Proxy-Authenticate |                       |
      |                              |                       |
HttpClient hỏi Authenticator:
    RequestorType = PROXY
    host/port của PROXY
      |
Policy xác minh proxy được phép và trả
PasswordAuthentication(proxyUser, proxyPassword)
      |
      | ----- Proxy-Authorization -->|                       |
      |                              | -- forward nếu hợp lệ >|
      |                              | <------- response ---- |
      | <--------- response -------- |                       |
~~~

**407 là challenge của proxy**, còn 401 là challenge của origin. RequestorType là một input thiết yếu khi chọn credentials; **host/port trong callback với PROXY liên quan proxy, không phải hostname website cuối**. Nếu bạn dùng cùng một Authenticator cho cả hai phía, điều kiện phân nhánh type phải rõ ràng.

Một HTTP proxy có thể nhận request ở **absolute-form** (ví dụ GET http://service.invalid/resource HTTP/1.1) hoặc yêu cầu **CONNECT** để tạo tunnel cho HTTPS. Hai chế độ có chính sách xác thực khác nhau ở Java JDK; sẽ phân tích riêng trong phần HTTPS proxy.

## 7. Chương trình Java 17 hoàn chỉnh: 401 origin và 407 proxy trên loopback

Demo tự mở **hai HTTP server cục bộ**, một đóng vai **origin** và một đóng vai **mock HTTP forward proxy**. Mock proxy **chỉ xác thực rồi tự trả một nội dung giả**, **không chuyển tiếp đến Internet**; nhờ vậy toàn bộ kết quả ổn định và không cần hostname bên ngoài phải resolve.

- Origin tại 127.0.0.1/cổng động: request đầu thiếu Authorization thì trả **401 + WWW-Authenticate: Basic**, request có header hợp lệ thì trả **ORIGIN_OK**.
- Mock proxy tại 127.0.0.1/cổng động: request thiếu Proxy-Authorization thì trả **407 + Proxy-Authenticate: Basic**, request có header hợp lệ thì trả **PROXY_OK**.
- HTTP client cho origin được cấu hình **NO_PROXY** và một Authenticator chỉ trả credentials nếu **RequestorType.SERVER** và host/port/scheme thuộc allowlist.
- HTTP client cho proxy được cấu hình **ProxySelector.of(...)** và Authenticator riêng chỉ cho **RequestorType.PROXY** và đúng proxy host/port/scheme.
- Credentials lab là student/lab-only, **không dùng trên mạng thật**. HTTP không mã hóa ở loopback; code này chỉ để quan sát challenge flow, không phải mẫu truyền mật khẩu qua Internet.
- Ứng dụng **không in password, Base64 auth header hoặc dynamic ports** để stdout ổn định.

Tạo tệp **AuthenticatorServerProxyDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.Authenticator;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public class AuthenticatorServerProxyDemo {
    private static String basic(String name, String password) {
        String userPass = name + ":" + password;
        return "Basic " + Base64.getEncoder().encodeToString(
                userPass.getBytes(StandardCharsets.ISO_8859_1));
    }

    private static void reply(HttpExchange exchange, int status,
                              String headerName, String body)
            throws IOException {
        if (headerName != null) {
            exchange.getResponseHeaders().set(headerName,
                    "Basic realm=\"java17-lab\"");
        }
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, data.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(data);
        } finally {
            exchange.close();
        }
    }

    private static Authenticator credentials(
            Authenticator.RequestorType allowedType,
            int allowedPort,
            AtomicReference<Authenticator.RequestorType> observed) {
        return new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                Authenticator.RequestorType type = getRequestorType();
                if (type != allowedType
                        || getRequestingPort() != allowedPort
                        || !"127.0.0.1".equals(getRequestingHost())
                        || !"basic".equalsIgnoreCase(getRequestingScheme())) {
                    return null;
                }
                observed.set(type);
                return new PasswordAuthentication(
                        "student", "lab-only".toCharArray());
            }
        };
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer origin = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        HttpServer proxy = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(4);
        origin.setExecutor(workers);
        proxy.setExecutor(workers);
        String expected = basic("student", "lab-only");

        origin.createContext("/protected", exchange -> {
            String auth = exchange.getRequestHeaders().getFirst("Authorization");
            if (!expected.equals(auth)) {
                reply(exchange, 401, "WWW-Authenticate", "AUTH_REQUIRED");
            } else {
                reply(exchange, 200, null, "ORIGIN_OK");
            }
        });

        proxy.createContext("/", exchange -> {
            String auth = exchange.getRequestHeaders().getFirst("Proxy-Authorization");
            if (!expected.equals(auth)) {
                reply(exchange, 407, "Proxy-Authenticate", "PROXY_AUTH_REQUIRED");
            } else {
                reply(exchange, 200, null, "PROXY_OK");
            }
        });

        origin.start();
        proxy.start();
        try {
            AtomicReference<Authenticator.RequestorType> serverType =
                    new AtomicReference<>();
            AtomicReference<Authenticator.RequestorType> proxyType =
                    new AtomicReference<>();
            int originPort = origin.getAddress().getPort();
            int proxyPort = proxy.getAddress().getPort();

            HttpClient serverClient = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .authenticator(credentials(
                            Authenticator.RequestorType.SERVER,
                            originPort, serverType))
                    .connectTimeout(Duration.ofSeconds(2))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpRequest serverRequest = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + originPort + "/protected"))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();
            HttpResponse<String> fromOrigin = serverClient.send(
                    serverRequest, HttpResponse.BodyHandlers.ofString());

            HttpClient proxyClient = HttpClient.newBuilder()
                    .proxy(ProxySelector.of(new InetSocketAddress(
                            loopback, proxyPort)))
                    .authenticator(credentials(
                            Authenticator.RequestorType.PROXY,
                            proxyPort, proxyType))
                    .connectTimeout(Duration.ofSeconds(2))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpRequest proxyRequest = HttpRequest.newBuilder(
                    URI.create("http://service.invalid/resource"))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> fromProxy = proxyClient.send(
                    proxyRequest, HttpResponse.BodyHandlers.ofString());

            System.out.println("Server status: " + fromOrigin.statusCode());
            System.out.println("Server body: " + fromOrigin.body());
            System.out.println("Authenticator type (server): " + serverType.get());
            System.out.println("Proxy status: " + fromProxy.statusCode());
            System.out.println("Proxy body: " + fromProxy.body());
            System.out.println("Authenticator type (proxy): " + proxyType.get());
        } finally {
            origin.stop(0);
            proxy.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 --add-modules jdk.httpserver AuthenticatorServerProxyDemo.java
java --add-modules jdk.httpserver AuthenticatorServerProxyDemo
~~~

Stdout trong lần chạy thành công:

~~~text
Server status: 200
Server body: ORIGIN_OK
Authenticator type (server): SERVER
Proxy status: 200
Proxy body: PROXY_OK
Authenticator type (proxy): PROXY
~~~

**Đã biên dịch với javac --release 17 và chạy thành công** trên JDK có module jdk.httpserver, kết quả khớp sáu dòng. Kết quả dựa vào local loopback và JDK HttpClient hỗ trợ Basic authentication qua HTTP trong môi trường lab. Không suy từ đó rằng HTTPS proxy tunneling có cùng policy với HTTP proxying.

### Giải thích từng bước trong demo

1. **HttpServer.create(...,0)** yêu cầu OS cấp cổng chưa sử dụng; hai servers không phụ thuộc port cố định. **HttpClient.Builder.NO_PROXY** giúp request đầu đi thẳng tới origin, không bị máy tính chuyển qua proxy mặc định.
2. **origin.createContext("/protected",...)** kiểm tra **Authorization** từ HTTP request. Nếu vắng/sai, trả 401 và **WWW-Authenticate**; nếu đúng, trả 200/ORIGIN_OK. Đây là phần server mock minh họa việc challenge, **không phải java.net.Authenticator chạy phía server**.
3. **proxy.createContext("/",...)** kiểm tra **Proxy-Authorization**. Trong demo, proxy được tạo bằng HttpServer nhưng không relay bytes; nó chỉ xác nhận client có tự động xử lý 407 và chọn đúng RequestorType.PROXY.
4. **getRequestorType()** được kiểm tra trong Authenticator, kèm **getRequestingHost**, **getRequestingPort** và **getRequestingScheme**. Một yêu cầu từ host/port/type không thuộc phạm vi sẽ nhận **null**, không có password.
5. **AtomicReference** chỉ lưu loại yêu cầu SERVER/PROXY để in kết quả; không lưu password. Trong hệ thống thật, Authenticator có thể được gọi trên thread khác và đồng thời; shared state phải thread-safe.
6. **HttpClient.Builder.authenticator** tách chính sách cho origin và proxy. **ProxySelector.of** chỉ dùng ở proxyClient, trong khi serverClient chọn NO_PROXY.
7. URI **http://service.invalid/resource** là một **đích giả có tên dành cho tài liệu**; mock proxy cục bộ tự trả response, không kết nối tới domain ấy. Nếu thay mock proxy bằng proxy thật, proxy sẽ phải forward và thực hiện DNS/network tới origin theo policy.
8. **HTTP 200 không đủ chứng minh remote service được ủy quyền**; nó chỉ xác nhận mock trong lab đã nhận header Basic như mong đợi. Một hệ thống production phải xác minh TLS, danh tính proxy/origin và authorization.
9. **Credentials hardcoded trong lab** và Base64 expected header bên server để kiểm thử flow. Không copy logic này vào server production: phải lưu password hash an toàn, dùng auth framework được kiểm thử, TLS và xử lý log/secret phù hợp.
10. **Server và proxy được đóng** trong finally; executor shutdownNow. Nếu loopback bị chặn hoặc JDK/provider khác xử lý proxy auth không như giả định, demo có thể báo IOException/timeout thay vì in sáu dòng.

## 8. Chương trình Java 17 thứ hai: kiểm tra phạm vi cấp credentials, không cần network

Để tách **policy của Authenticator** khỏi network timing và HTTP challenge, Java cung cấp phương thức **Authenticator.requestPasswordAuthentication(Authenticator, host, addr, port, protocol, prompt, scheme, url, RequestorType)**. Có thể dùng nó để **kiểm thử trực tiếp một instance Authenticator** mà không thực sự phát HTTP request.

Chương trình sau chỉ cho phép trả credentials khi:

- RequestorType chính xác là **PROXY**.
- Host chính xác là **127.0.0.1**.
- Port chính xác là **8888**.
- Authentication scheme là **Basic** (so sánh không phân biệt chữ hoa/thường).

Mọi yêu cầu kiểu SERVER hoặc sai proxy host/port đều **return null**. Mật khẩu lab không được in.

Tạo tệp **AuthenticatorPolicyDemo.java**:

~~~java
import java.net.Authenticator;
import java.net.InetAddress;
import java.net.PasswordAuthentication;
import java.util.Arrays;

public class AuthenticatorPolicyDemo {
    private static final class ScopedAuthenticator extends Authenticator {
        @Override
        protected PasswordAuthentication getPasswordAuthentication() {
            if (getRequestorType() != RequestorType.PROXY
                    || !"127.0.0.1".equals(getRequestingHost())
                    || getRequestingPort() != 8888
                    || !"basic".equalsIgnoreCase(getRequestingScheme())) {
                return null;
            }
            return new PasswordAuthentication(
                    "proxy-user", "lab-only".toCharArray());
        }
    }

    private static PasswordAuthentication ask(
            Authenticator auth, String host, int port,
            Authenticator.RequestorType type) throws Exception {
        return Authenticator.requestPasswordAuthentication(
                auth, host, InetAddress.getByName("127.0.0.1"),
                port, "http", "lab", "Basic", null, type);
    }

    public static void main(String[] args) throws Exception {
        Authenticator auth = new ScopedAuthenticator();
        PasswordAuthentication allowed = ask(
                auth, "127.0.0.1", 8888, Authenticator.RequestorType.PROXY);
        System.out.println("Expected proxy: " + (allowed != null));
        System.out.println("Proxy username: " + allowed.getUserName());

        System.out.println("Server request denied: " + (ask(
                auth, "127.0.0.1", 8888,
                Authenticator.RequestorType.SERVER) == null));
        System.out.println("Wrong proxy port denied: " + (ask(
                auth, "127.0.0.1", 9999,
                Authenticator.RequestorType.PROXY) == null));
        System.out.println("Wrong proxy host denied: " + (ask(
                auth, "other.invalid", 8888,
                Authenticator.RequestorType.PROXY) == null));
        char[] retrieved = allowed.getPassword();
        System.out.println("Password provided: " + (retrieved.length > 0));
        Arrays.fill(retrieved, '\0');
    }
}
~~~

~~~bash
javac --release 17 AuthenticatorPolicyDemo.java
java AuthenticatorPolicyDemo
~~~

Stdout:

~~~text
Expected proxy: true
Proxy username: proxy-user
Server request denied: true
Wrong proxy port denied: true
Wrong proxy host denied: true
Password provided: true
~~~

**Đã biên dịch với javac --release 17 và chạy thành công.** Chương trình **không kết nối tới other.invalid**: đó chỉ là một chuỗi host truyền vào callback để kiểm thử chính sách. Trường hợp gọi getPassword() và **Arrays.fill** minh họa trách nhiệm làm sạch mảng đã lấy từ PasswordAuthentication; nó không chứng minh có thể xóa mọi bản sao hoặc bí mật lưu ngoài mảng. Không in hoặc lưu password thật.

### Điều quan trọng về requestPasswordAuthentication

Một chương trình kiểm thử **Authenticator.requestPasswordAuthentication(...)** gọi policy trực tiếp, nhưng **không** chứng minh một HTTP client/provider hỗ trợ tất cả schemes hoặc sẽ tạo callback trong mọi trường hợp. Cần **unit test policy** và **integration test thật với HTTP challenge**. Chương trình đầu giải quyết integration test trong lab; chương trình thứ hai kiểm tra policy độc lập.

## 9. Thiết kế Authenticator an toàn trong sản phẩm thật

Nếu triển khai một ứng dụng gọi cả nhiều origin APIs và proxy doanh nghiệp, một Authenticator nên giới hạn credentials bằng identity và route phù hợp:

~~~text
Authentication challenge
        |
        v
getRequestorType() == SERVER hay PROXY?
        |
        +-- SERVER:
        |     allowlisted origin + port + scheme + realm?
        |        |
        |        +-- no --> null
        |        +-- yes -> secret provider cho origin ấy
        |
        +-- PROXY:
              allowlisted proxy + port + scheme + realm?
                 |
                 +-- no --> null
                 +-- yes -> secret provider cho proxy ấy
~~~

Các trường context như host/port/scheme có thể null/không cố định tùy request và provider. Một policy tốt cần **fail-closed** khi không chứng minh được endpoint phù hợp. Đừng dùng điều kiện quá rộng như host.endsWith("example.com") nếu nó chấp nhận **evil-example.com**; phải so host chuẩn hóa hoặc đúng subdomain boundary, và phải cẩn thận IDN/punycode, IPv4/IPv6 và thay đổi cổng.

### Quy tắc phân tách secrets

- **Origin credentials:** có scope cho API origin cụ thể và thông thường chỉ được dùng qua HTTPS tới host được phê duyệt.
- **Proxy credentials:** chỉ dùng cho proxy định danh cụ thể, không bao giờ dùng để tạo Authorization header gửi đến origin.
- **Realm:** có thể dùng như một phần khóa tra cứu nhưng **realm do bên yêu cầu cung cấp** và không phải danh tính mật mã độc lập.
- **Auth scheme:** không tự rơi xuống Basic khi server đổi policy hoặc xuất hiện một scheme lạ; áp danh sách schemes được duyệt.
- **Tenant/service identity:** nếu hai tenants dùng cùng HttpClient/proxy nhưng secrets khác nhau, cần thiết kế tách Authenticator/client theo security boundary để tránh lẫn quyền.
- **Secret source:** secrets manager, injected credentials, key rotation hoặc một provider được kiểm soát; không commit password vào Git hoặc image.

**Đừng tự động đưa PasswordAuthentication cho mọi URL do người dùng nhập.** Nếu URL có thể được điều khiển từ bên ngoài, kẻ tấn công có thể dựng server trả 401 để lôi Authenticator cấp credentials. Cần allowlist, proxy rules, redirect restrictions, TLS verification và tách security contexts.

### Thread safety và tránh blocking callback

Một HttpClient có thể gửi nhiều requests đồng thời; Authenticator có thể được gọi trên threads khác nhau. Vì vậy:

- Dữ liệu policy nên **immutable** hoặc thread-safe.
- Không lưu một biến toàn cục kiểu **currentHost/currentPassword** và giả định mỗi request hoàn tất tuần tự.
- Có thể dùng cache secret theo scope, nhưng **TTL, rotation, revocation** phải rõ ràng.
- Nếu password provider liên hệ hệ thống quản lý bí mật chậm, callback có thể trở thành bottleneck; nạp secrets an toàn từ trước hoặc dùng cơ chế không chặn phù hợp với kiến trúc, không bắt người dùng nhập mật khẩu bằng dialog trên server không có UI.
- Không log request context kèm credentials hoặc challenge headers nhạy cảm; log chỉ loại SERVER/PROXY, host/port đã mask, error reason và correlation id.

## 10. HTTPS qua proxy, CONNECT và chính sách Basic

**HTTP proxying** và **HTTPS tunneling** không giống nhau.

### HTTP origin qua forward proxy

Đối với URL **http://...**, client thường gửi HTTP request tới proxy với absolute URI (theo HTTP/1.1 proxy semantics). Proxy có thể 407/Proxy-Authenticate và client trả Proxy-Authorization. Nếu **proxy transport là HTTP plaintext**, Basic credentials gửi tới proxy có thể quan sát được trên đường truyền: **không dùng chúng qua mạng không tin cậy**. Bài lab sử dụng loopback để tránh phát credentials ra mạng thật.

### HTTPS origin qua HTTP proxy

Đối với URL **https://...**, một flow thường là:

~~~text
Client --- CONNECT origin:443 ---> HTTP proxy
        <--- 407 Proxy-Authenticate? ---
        --- Proxy-Authorization? ---->
        <--- 200 Connection Established ---
                  |
                  +--- TLS handshake tới origin qua tunnel
                  |
                  +--- HTTPS request/response mã hóa TLS
~~~

**HTTPS đến origin không tự mã hóa thông điệp xác thực gửi cho proxy trước khi tunnel được thiết lập.** Nếu dùng Basic credentials tới một proxy không có transport được bảo vệ, chúng có thể bị lộ, dù traffic bên trong tunnel về sau có TLS. Hãy dùng kiến trúc proxy và phương thức xác thực đã được tổ chức phê duyệt (có thể gồm VPN/mTLS/secure proxy). Đừng coi có biểu tượng HTTPS ở đích là chứng cứ mọi hop đều bí mật.

### Giới hạn JDK liên quan Basic với CONNECT

Tài liệu **Java 17 Networking System Properties** cho biết:

- **jdk.http.auth.tunneling.disabledSchemes** mặc định liệt kê **Basic**. Scheme bị liệt kê có thể **không được dùng khi tunneling HTTPS qua HTTP CONNECT**.
- **jdk.http.auth.proxying.disabledSchemes** dùng cho HTTP proxying thường; mặc định không có giá trị disabled scheme được khai báo trong tài liệu.
- Đây là các **system/security properties cấp JDK** và hành vi có thể khác theo provider/JDK configuration.

Vì vậy **demo HTTP proxy trả 407 ở phần trước không chứng minh Basic hoạt động với HTTPS CONNECT** trong mọi JDK. Nếu proxy công ty yêu cầu Basic qua CONNECT mà client không authenticate, cần kiểm tra logs, loại proxy tunnel và chính sách của JVM; không lập tức kết luận code Authenticator sai.

**Không tự động xóa Basic khỏi danh sách disabled schemes trong production chỉ để sửa handshake.** Đó có thể là hạ cấp chính sách bảo mật. Cần đánh giá transport tới proxy, phương thức auth và yêu cầu tuân thủ. Nếu tổ chức chấp thuận thay đổi cấu hình, kiểm chứng ở môi trường có kiểm soát và ghi lại rủi ro.

## 11. Authenticator và các HTTP headers: không tự trộn hai cơ chế

Khi dùng Authenticator cho HTTP challenge, networking implementation có thể quản lý việc tạo **Authorization** hoặc **Proxy-Authorization** theo scheme. Nếu đồng thời ứng dụng tự đặt thủ công các headers này, có thể xảy ra:

- Header đặt thủ công được ưu tiên, không kích hoạt Authenticator cho yêu cầu tương ứng.
- Header bị từ chối hoặc behavior phụ thuộc JDK/provider.
- Request mang credentials sai origin sau redirect.
- Rủi ro cache/leak credentials khi lặp lại request.

Tài liệu Java Networking của Oracle cảnh báo **Authorization** có ràng buộc đặc biệt khi HttpClient có Authenticator. **Đừng dựa vào một cơ chế override restricted headers cho production**. Chọn một chiến lược xác thực rõ: **challenge-response qua Authenticator** cho schemes được hỗ trợ, hoặc **explicit auth headers** có scope rõ ràng nếu giao thức yêu cầu (ví dụ bearer token), nhưng phải kiểm tra đúng API/JDK.

### Challenge không phải login session

**PasswordAuthentication** không tự tạo một phiên đăng nhập (cookie/session). Nếu origin server trả **Set-Cookie** sau Basic auth, việc quản lý cookie thuộc HTTP client CookieHandler/ứng dụng và server. Có thể cần token/session lifecycle riêng; **đừng suy mọi request về sau đều không cần xác thực** chỉ vì một request trước trả 200.

**401** không đồng nghĩa “username/password của bạn chắc chắn sai”; nó cũng có thể do thiếu credentials, realm/scheme không hỗ trợ, policy khác, token hết hạn hoặc một server config bug. **403 Forbidden** thường thể hiện server từ chối authorization dù đã xác định danh tính, nhưng vẫn phải đọc API contract để phân loại chính xác.

## 12. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý phù hợp |
|---|---|---|
| HttpResponse.statusCode() == **401** | Origin yêu cầu xác thực/credentials không được chấp nhận | Kiểm tra WWW-Authenticate, Authenticator.SERVER, đúng host/port/realm, scheme |
| HttpResponse.statusCode() == **407** | Proxy yêu cầu xác thực | Kiểm tra Proxy-Authenticate, ProxySelector, Authenticator.PROXY, proxy host/port |
| Authenticator callback không chạy | Chưa có challenge, không set authenticator, scheme bị disable/không hỗ trợ, manual header hoặc cache | Kiểm tra config và traffic có kiểm soát, không suy đoán |
| Callback có chạy nhưng trả null | Policy allowlist không khớp hoặc secret provider từ chối | Kiểm tra RequestorType, host/port/scheme/realm trong log đã mask |
| Callback trả credentials nhưng vẫn 401/407 | Sai user/password, realm, scheme, provider hoặc policy server/proxy | Dừng retry mù, xác minh account/trust, rate limit |
| HTTP 403 | Tầng ứng dụng/proxy từ chối quyền | Không tự gửi thêm password đến host lạ |
| IOException/ConnectException | Lỗi mạng/proxy route/port, không chắc lỗi credentials | Kiểm tra DNS, proxy address, firewall, timeout |
| SSLHandshakeException | TLS certificate/trust/hostname/cipher không hợp lệ | Sửa trust/PKI, không bật trust-all |
| CONNECT qua proxy bị 407 với Basic | Basic tunneling có thể bị disabled theo JVM policy | Kiểm tra jdk.http.auth.tunneling.disabledSchemes và thiết kế proxy |
| Authenticator lộ secrets trong logs | Log password, Authorization header, URI userinfo, exception payload | Mask/remove logs, rotate secret và audit |
| Nhiều authentication retries | Credentials sai hoặc server không chấp nhận challenge flow | Giới hạn retries, kiểm tra server logs, chống brute-force |
| Không có proxy dù đã cấu hình OS | Java proxy properties/default selector khác expectation | Đặt ProxySelector tường minh nếu cần, kiểm tra Java 17 config |

### Checklist khi gỡ lỗi 401/407

1. Request có đi **đúng origin hoặc đúng proxy** không? Có redirect hay proxy auto-config không?
2. Status thực sự là 401 hay 407? Header **WWW-Authenticate** hay **Proxy-Authenticate** nào xuất hiện?
3. Đã **authenticator(...)** trên đúng HttpClient đang gửi request chưa?
4. **getRequestorType()** ở callback là SERVER hay PROXY?
5. Host và port callback có đúng target theo chính sách, không phải host ban đầu khi đã redirect?
6. Scheme được hỗ trợ/chấp nhận không? **getRequestingScheme()** là Basic hay scheme khác?
7. Có chặn credentials ở allowlist/realm (trả null) không?
8. Username/password lấy từ secret provider có hết hạn, sai scope hoặc đang rotate không?
9. Có ứng dụng đang tự set Authorization/Proxy-Authorization khiến HttpClient không dùng flow expected không?
10. Nếu HTTPS qua proxy, CONNECT có bị chặn scheme Basic theo JDK config không?
11. Kết nối tới origin/proxy có TLS đúng, certificate/hostname verification hợp lệ và transport tới proxy được bảo vệ không?
12. Client/server logs có chứa secrets hoặc hiển thị password trong URL không? Nếu có, cần xử lý sự cố rò rỉ.

### Không đồng nhất status với Java exception

**401/407 thường là HTTP responses bình thường theo HTTP protocol**, không tự biến thành một lớp exception riêng của java.net.http. Tầng Authenticator có thể thử xử lý challenge; nếu không thành công, client có thể trả response status 401/407 hoặc báo một lỗi theo implementation. Code nghiệp vụ phải luôn **kiểm tra statusCode** và **xử lý IOException/InterruptedException**. Không viết code “nếu send không ném exception thì đã login thành công”.

## 13. Security: Basic, HTTPS, proxy credentials và secret lifecycle

### Không dùng Basic qua mạng không bảo vệ

Basic có thể bị đảo Base64 thành username/password. Với origin, dùng **HTTPS**, certificate chain và hostname verification; không tắt kiểm tra TLS để vượt lỗi. Với proxy, **kiểm soát đường tới proxy** và hỗ trợ xác thực bảo mật theo chính sách doanh nghiệp. HTTPS tunnel tới origin không tự bảo vệ Basic credentials được gửi tới proxy trước CONNECT.

### Giới hạn phạm vi credentials

- Tách usernames/passwords cho proxy và origin.
- Phân theo host/port và auth method; từ chối môi trường test/staging nếu production secret không được phép dùng tại đó.
- Không cấp credential vào host khác sau redirect, chỉ vì nó cùng top-level domain.
- Nếu user nhập tùy ý URL, chống SSRF, DNS rebinding và các endpoint private nội bộ ngoài allowlist.
- Không tạo Authenticator toàn cục trả default admin password cho bất cứ caller nào.

### Rotation và invalidation

Authenticator thường đọc secret từ memory/provider. Nếu password rotate, có thể cần làm mới secret provider/cache, tạo HttpClient/config theo policy hoặc đóng connections có auth context cũ. **Không giả định Java HttpClient lập tức quên mọi cached authentication state khi file secret được thay trên đĩa**. Không hardcode/password reuse trong production, không tiết lộ credentials qua telemetry.

### Giới hạn việc ghi log

Ghi **RequestorType, alias của endpoint, challenge scheme, status, latency, attempt count**, correlation ID và error reason đã lọc; không ghi **PasswordAuthentication.getPassword()**, HTTP Authorization/Proxy-Authorization, cookie hoặc token. Nếu bật Java HTTP debug logs, kiểm tra chính sách redaction và storage access trước.

### Sử dụng char[] thực tế

Tạo char[] từ secret provider khi cần, hạn chế thời gian tồn tại và xóa **những mảng bạn sở hữu** sau khi API sử dụng xong. Tuy nhiên PasswordAuthentication **sao chép đầu vào** và getPassword trả **reference** tới mảng bên trong; đừng xóa mảng ấy trước khi HTTP client kịp dùng nó hoặc giữ object không rõ lifetime. Không xem char[] là đủ chống memory dump; secret isolation, process privileges và TLS vẫn thiết yếu.

## 14. Khi nào không nên dùng PasswordAuthentication?

Có những trường hợp cần cơ chế khác:

| Trường hợp | Phương pháp thường phù hợp hơn |
|---|---|
| API dùng OAuth2 access token/JWT | Token provider + Authorization: Bearer, refresh lifecycle |
| Dịch vụ service-to-service dùng mTLS | SSLContext/client certificates, kiểm tra identity/authorization |
| Web login có cookie và CSRF | CookieManager/client/session framework và CSRF policy |
| HTTP server cần kiểm tra request đến | Server-side auth filter, BasicAuthenticator/Servlet Security/Spring Security |
| Kết nối proxy yêu cầu SSO/Kerberos | Thư viện/provider hoặc enterprise proxy stack phù hợp, kiểm chứng JDK hỗ trợ |
| Cần phân quyền theo vai trò | Authorization ở ứng dụng/policy engine, không phải chỉ cấp Basic credentials |
| Proxy có nhiều schemes/phương thức đặc thù | SDK cấu hình proxy được tổ chức xác nhận, không tự giả lập header |

**com.sun.net.httpserver.BasicAuthenticator** (trong module jdk.httpserver) là **server-side authenticator** khác với **java.net.Authenticator**. Tên gần giống nhưng vai trò khác: một bên kiểm tra credentials nhận vào, một bên cung cấp credentials để client đáp ứng challenge.

Nếu một chương trình cần gửi **Bearer** tới origin và **Basic** tới proxy, hãy kiểm soát hai cơ chế riêng. Đừng dùng một PasswordAuthentication để lưu cả token và password rồi kỳ vọng HttpClient tự hiểu format.

## 15. Hiệu năng, retry và concurrency

### Authentication thêm round-trip

Trong flow challenge-response, request đầu có thể nhận 401/407 rồi request khác được gửi cùng credentials. Chi phí thêm network round-trip và có thể ảnh hưởng latency. Proxy chaining, TLS handshake, server processing và authentication cache làm thời gian thực khác nhau. **Không dùng “đã login trước” như đảm bảo mọi request sau sẽ không bị challenge lại**.

### Giới hạn retry

Nếu credentials sai, tự retry liên tục có thể khóa account, gây rate limit hoặc làm bão network. Thiết kế **bounded attempts**, auth failure metrics, backoff/lockout policy và phân biệt lỗi network tạm thời với lỗi 401/407 không thể tự sửa. Một credential invalid không nên được retry mãi ở nhiều requests song song.

### Không tự động replay POST có side effects

Một authentication challenge có thể đòi gửi lại request; đối với POST/PUT có body một-lần và side effects, cần hiểu khả năng replay của BodyPublisher, trạng thái server đã đọc/xử lý bao nhiêu bytes và idempotency policy. **Đừng mặc định mọi HTTP request đều có thể replay an toàn sau khi gặp 401/407**. Với nghiệp vụ thanh toán/tạo đơn, dùng idempotency key và reconciliation để tránh nhân đôi tác vụ.

### Thread-safety

Một HttpClient có thể phục vụ nhiều requests; Authenticator callback có thể chạy đồng thời. Khi dùng cấu hình credential cache hoặc metrics trong callback, tránh mutable global variables không đồng bộ; ví dụ lab dùng **AtomicReference** để quan sát loại request. Trong production, có thể cần immutable credential map và per-endpoint secret provider thread-safe.

### Timeouts tách biệt

**HttpClient.Builder.connectTimeout(Duration)** giới hạn việc thiết lập connection mới; **HttpRequest.Builder.timeout(Duration)** giới hạn chờ response từng request. Chúng không tự thay thế **authentication challenge timeout**, **proxy CONNECT policy**, **overall business deadline** hoặc **secret provider latency**. Thêm deadline tổng cho nhiều retries và network hops; quan sát connection/authentication timings.

## 16. Test matrix: phải có cả đường âm

| Test | Đầu vào/kịch bản | Điều cần xác minh |
|---|---|---|
| Origin challenge | 401 + WWW-Authenticate: Basic | SERVER Authenticator cấp đúng credentials, nhận 200 |
| Proxy challenge | 407 + Proxy-Authenticate: Basic | PROXY Authenticator cấp đúng proxy credentials, nhận 200 |
| Không có Authenticator | Gọi origin /protected | Có thể nhận 401, không gửi credentials ngầm |
| Wrong password | Trả PasswordAuthentication sai | Không thể tự động trở thành authenticated response |
| Wrong origin host | Policy không allowlist | **return null**, không tiết lộ secret |
| Wrong proxy port | Proxy host đúng nhưng port sai | **return null** |
| Wrong RequestorType | SERVER credentials bị hỏi ở PROXY | **return null** |
| Unsupported auth scheme | Scheme không được phê duyệt | Không tự cấp credentials |
| Redirect cross-origin | URL từ host A chuyển sang host B | Không phát secret của A sang B |
| Multiple proxies | ProxySelector chọn proxy khác | Chọn credentials chính xác theo proxy |
| HTTPS CONNECT proxy | Proxy yêu cầu Basic qua tunnel | Kiểm tra disabledSchemes, không hạ security |
| No listener | Sai proxy/origin address | Phân loại ConnectException/IOException thay vì auth failure |
| Proxy trả 403 | Bị policy từ chối | Không retry vô hạn bằng credentials khác |
| Password rotation | Secret cũ hết hiệu lực | Có thể reload theo policy, không giữ cached state sai |
| Concurrent requests | N callbacks cùng lúc | Không lẫn host, port, user, tenant hoặc secret |

**Test code quan trọng hơn việc nhìn status 200 đơn lẻ.** Một proxy trả 200 trong mock không chứng minh proxy đã forward bytes ra origin, vì mock của demo cố ý không forward. Khi chạy integration test thật phải xác minh **đúng hop**, đúng endpoint và policies đã được thi hành.

### Test logging

Thử tạo failed auth và kiểm tra logs chỉ chứa status/type/scheme/endpoint alias. Không chứa Basic base64, password, URI userinfo, token/cookie. Trong kiểm thử security nên chạy secret scanners và masking tests lên logs/traces.

## 17. Các bài tập thực hành

### Bài tập A — Thấy 401 thực sự

Chạy **AuthenticatorServerProxyDemo.java**. Tạm thời bỏ **authenticator(...)** ở serverClient, giữ NO_PROXY. Dự đoán request /protected trả status gì, và vì sao không có PasswordAuthentication nào được tạo cho origin. Sau đó phục hồi và kiểm tra status 200.

### Bài tập B — Thấy 407 thực sự

Bỏ Authenticator khỏi proxyClient nhưng giữ **ProxySelector.of(...)**. Xác minh mock proxy trả 407. Phân tích lý do API không thể “mượn” credentials của originClient nếu không được cấu hình; gắn lại policy PROXY thì nhận 200.

### Bài tập C — Kiểm tra type/port

Chạy **AuthenticatorPolicyDemo.java**, thử thay port 8888 thành 9999 hoặc chuyển RequestorType.PROXY sang SERVER. Viết assertions thay vì chỉ in output, đảm bảo mọi type/port ngoài allowlist trả null.

### Bài tập D — Thêm realm policy

Trong Authenticator, kiểm tra thêm **getRequestingPrompt()** với realm đã cấu hình trong lab. Cố ý đổi realm ở server, chứng minh policy từ chối credentials. Lưu ý realm không có tính bảo mật riêng; nó chỉ giúp namespace credentials.

### Bài tập E — Tách secrets hai phía

Thay student/lab-only bằng hai cặp **lab-origin/lab-origin-only** và **lab-proxy/lab-proxy-only**. Sửa hai HTTP server mock để xác nhận đúng bộ tương ứng. Nếu tráo hai cặp, cả origin/proxy phải từ chối.

### Bài tập F — Concurrent requests

Dùng **sendAsync** cho nhiều requests tới /protected qua cùng HttpClient với Authenticator scoped, in kết quả sau **CompletableFuture.allOf**. Bảo đảm không dùng biến mutable toàn cục currentHost/currentPassword; thử đo callback count nhưng không giả định số lần callback = số requests.

### Bài tập G — HTTPS và Basic

Trong lab TLS riêng, tạo server HTTPS có cert/hostname tin cậy và Basic challenge, client dùng SSLContext phù hợp. Xác nhận username/password chỉ xuất hiện trong TLS application data, không lộ trên plaintext HTTP; không tắt certificate verification.

### Bài tập H — Proxy CONNECT policy

Với một HTTP proxy thử nghiệm do bạn kiểm soát, so sánh HTTP proxying thông thường và CONNECT HTTPS tunneling, kiểm tra **jdk.http.auth.tunneling.disabledSchemes** ở JDK 17. Giải thích tại sao Basic cho HTTP proxy có thể hoạt động trong khi Basic cho CONNECT mặc định bị disable. Không tắt chính sách bảo mật trên mạng thật để hoàn thành test.

### Bài tập I — Token vs PasswordAuthentication

Một API dùng **Bearer token**, proxy yêu cầu **Basic**. Thiết kế cách cấu hình token provider cho origin và Authenticator scoped PROXY riêng; không cho Proxy-Authorization lẫn Authorization và không log bất kỳ secrets nào.

### Bài tập J — Redirect và SSRF

Cho server A redirect tới server B thuộc mạng lab. Kiểm tra Authenticator allowlist từ chối cung cấp origin credentials của A cho B, bất kể B cũng gửi WWW-Authenticate. Thảo luận về DNS rebinding, IP/private network egress policy và redirect allowlist.

## 18. Câu hỏi tự kiểm tra

**1. java.net.Authenticator nằm ở server hay client trong bài này?** Ở phía **client**, nó cấp credentials khi bên ngoài yêu cầu xác thực. Không thay cho server-side verification.

**2. PasswordAuthentication chứa gì?** Username String và password char[], không tự gửi HTTP request hoặc xác minh tài khoản.

**3. Origin trả status nào để yêu cầu xác thực HTTP?** **401 Unauthorized**, thường kèm **WWW-Authenticate**.

**4. Proxy trả status nào để yêu cầu xác thực?** **407 Proxy Authentication Required**, kèm **Proxy-Authenticate**.

**5. Client gửi origin credentials trong header nào?** **Authorization**.

**6. Client gửi proxy credentials trong header nào?** **Proxy-Authorization**.

**7. getRequestorType() có những giá trị nào?** **SERVER** và **PROXY**.

**8. getRequestingScheme() == "Basic" nghĩa URI đang dùng HTTP?** Không. "Basic" là HTTP authentication scheme, khác URI protocol "http"/"https".

**9. Nếu host/type không khớp allowlist, Authenticator nên trả gì?** **null**, tức không cấp credentials.

**10. Có thể dùng một Authenticator trả admin password cho mọi challenge không?** Không nên; rủi ro lộ password sang host/proxy không đáng tin.

**11. Basic có bảo mật chỉ nhờ Base64 không?** Không. Base64 là encoding có thể giải; cần transport TLS phù hợp và chính sách bảo mật.

**12. 401/407 có tự động gây IOException trong mọi Java HttpClient không?** Không. Có thể chỉ là một HttpResponse có status tương ứng; phải kiểm tra statusCode.

**13. HttpClient.Builder.NO_PROXY có tác dụng gì?** Chọn kết nối trực tiếp, tránh proxy default.

**14. ProxySelector.of(...) có tự đăng nhập vào proxy không?** Không. Nó chỉ chọn proxy; Authenticator/credentials xử lý xác thực.

**15. Vì sao PasswordAuthentication.getPassword() cần cẩn thận?** Nó trả tham chiếu tới mảng password; không để lộ, lưu/log hay xóa trước khi client đã dùng.

**16. Một HttpClient có thể cần hai loại credentials không?** Có, nếu gặp cả origin 401 và proxy 407. Phải tách theo RequestorType và endpoint.

**17. HTTPS tới origin có tự mã hóa credentials Basic gửi tới proxy trước CONNECT không?** Không. Cần xét riêng transport và security boundary tới proxy.

**18. Vì sao Basic qua CONNECT có thể không hoạt động dù Basic proxy HTTP chạy?** Java 17 JDK có property **jdk.http.auth.tunneling.disabledSchemes** mặc định tắt Basic cho CONNECT tunneling.

**19. Authenticator.setDefault nên dùng vô điều kiện trong server nhiều tenants?** Không. Cấu hình JVM-wide có thể cấp credentials sai phạm vi; ưu tiên per-HttpClient scoped authenticator.

**20. Có thể dùng PasswordAuthentication thay cho OAuth Bearer token không?** Không tự động. Bearer token là một cơ chế auth khác cần provider/header/lifecycle riêng.

## Tài liệu tham khảo chính thức Java 17 và HTTP

- **Java SE 17 — java.net.Authenticator:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Authenticator.html
- **Java SE 17 — java.net.PasswordAuthentication:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/PasswordAuthentication.html
- **Java SE 17 — HttpClient.Builder (authenticator và proxy):** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- **Java SE 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java SE 17 — ProxySelector:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html
- **Java SE 17 — Networking System Properties:** https://docs.oracle.com/en/java/javase/17/core/java-networking.html
- **Java SE 17 — HttpResponse:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- **RFC 9110 — HTTP Semantics (401, 407 và xác thực):** https://www.rfc-editor.org/rfc/rfc9110
- **RFC 7617 — The 'Basic' HTTP Authentication Scheme:** https://www.rfc-editor.org/rfc/rfc7617

**Ghi nhớ:** **Authenticator** là callback giúp Java HTTP client cung cấp credentials khi **origin server (SERVER/401)** hoặc **proxy (PROXY/407)** yêu cầu xác thực; **PasswordAuthentication** giữ username/char[] password để client dùng trong scheme được hỗ trợ. **Authorization** dành cho origin, **Proxy-Authorization** dành cho proxy. Không trả mật khẩu cho mọi challenge: **xác minh RequestorType, host, port, scheme, realm và trust policy**, giữ secret ngoài source code, bảo vệ transport bằng TLS phù hợp, xử lý timeout/retry và kiểm tra statusCode. Cấu hình **HttpClient.Builder.authenticator(...)** theo từng security boundary thường an toàn hơn một Authenticator toàn JVM, và **Basic authentication qua proxy CONNECT có policy riêng** cần kiểm tra trên Java 17.