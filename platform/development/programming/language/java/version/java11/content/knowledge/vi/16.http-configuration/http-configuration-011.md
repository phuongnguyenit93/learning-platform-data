# Kiểm thử proxy, redirect và phiên độc lập với Java HTTP Client (Java 11+)

## 1. Mục tiêu của bài: kiểm tra cấu hình HTTP bằng bằng chứng thực tế

Một `HttpClient` có thể dùng proxy, tự theo HTTP redirect và xử lý cookie/session nếu ứng dụng cung cấp `CookieHandler`. Những hành vi này đều nằm ở ranh giới giữa **cấu hình của client**, **đường đi của request**, **phản hồi của server** và **trạng thái do ứng dụng sở hữu**. Chỉ nhìn vào `HttpClient.Builder` không đủ để biết chương trình thực sự đi qua proxy nào, theo bao nhiêu lần redirect hay có vô tình dùng chung cookie của tài khoản khác hay không.

Bài này dùng các API **`java.net.http` của Java 11**, vẫn được hỗ trợ ở JDK hiện hành, để giải quyết ba bài toán kiểm thử:

1. **Proxy** — xác nhận request dùng đường đi proxy được cấu hình hoặc đi thẳng khi `NO_PROXY`; không tự suy luận từ việc builder gọi `proxy(...)`.
2. **Redirect** — phân biệt policy `NEVER`/`NORMAL`/`ALWAYS`, kiểm tra mã HTTP 3xx, `Location`, URI đích, `previousResponse()` và những tác động có thể xảy ra với method/credential.
3. **Phiên độc lập (session isolation)** — chứng minh mỗi client/nhóm người dùng có `CookieManager` riêng khi cần, và một session cookie tạo ở client A **không xuất hiện** trong request của client B.

Cần hiểu **phiên** trong bài là **trạng thái đăng nhập/HTTP cookie do ứng dụng quản lý**, không phải một loại giao thức phiên đặc biệt được `HttpClient` tự tạo. Connection pooling, TLS session, cookie jar, request header và token ứng dụng là các khái niệm khác nhau. Không được coi “tạo hai object `HttpClient`” là phép bảo đảm mọi dữ liệu liên quan đều tự cách ly nếu vẫn dùng chung các object cấu hình mutable.

### Kết quả cần quan sát

~~~text
            HTTP Client A               HTTP Client B
             |      |                        |
             |      +---- CookieManager A    +---- CookieManager B
             |                               |
             +-- proxy / redirect policy     +-- proxy / redirect policy riêng
                          |
                       HTTP request
                          |
                 +--------+--------+
                 |                 |
             proxy server      origin server
                 |                 |
          log/nhận request   302, Set-Cookie, echo Cookie
                 |                 |
                 +--------+--------+
                          |
                 HttpResponse<T>
               status / headers / uri / body
                          |
                 Đối chiếu assert kết quả
~~~

Trong test tốt, **server/proxy là fixture do test kiểm soát**, request đi trên loopback và response được định nghĩa trước. Cách này tránh phụ thuộc Internet, proxy công ty, trình duyệt, clock hoặc dịch vụ của bên thứ ba.

## 2. Phân biệt cấu hình thuộc client, request và response

### `HttpClient`: cấu hình dùng lại qua nhiều requests

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .followRedirects(HttpClient.Redirect.NORMAL)
        .proxy(HttpClient.Builder.NO_PROXY)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

**Mã minh họa**, cần imports `HttpClient` và `Duration`, đặt trong lớp/method. Các lựa chọn này thuộc một **client instance**. `HttpClient` được tạo qua builder có cấu hình bất biến sau `build()` và có thể dùng nhiều lần. Builder là mutable và **không thread-safe** khi bị thay đổi đồng thời.

Các thuộc tính có thể kiểm tra:

~~~java
client.followRedirects();          // Redirect.NORMAL trong ví dụ
client.proxy().isPresent();        // true do đã cung cấp selector tường minh
client.version();                  // Phiên bản HTTP ưu tiên
client.cookieHandler().isPresent();// false nếu chưa cấu hình CookieHandler
~~~

**Mã minh họa**: gọi `client.proxy().isPresent()` chỉ xác nhận có `ProxySelector` **được truyền rõ ràng**; nó **không xác nhận request thực sự qua proxy**, và `Optional.empty()` cũng **không bảo đảm không có proxy mặc định**. Để bắt buộc đi thẳng trong phép thử, hãy dùng `HttpClient.Builder.NO_PROXY` thay vì phụ thuộc cấu hình mạng của máy chạy.

### `HttpRequest`: mô tả từng lần gọi

~~~java
HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.com/items"))
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Request ở đây là **đoạn minh họa cấu hình**, chưa gửi ra Internet. URI, method, headers và request timeout nằm ở `HttpRequest`. Nó **không tự chứa cookie jar**; cookie nếu có được lấy theo `CookieHandler` của client và các điều kiện domain/path/secure của cookie.

### `HttpResponse<T>`: bằng chứng ở đầu nhận

Sau `send(...)` hoặc `sendAsync(...)`:

| Thuộc tính | Ý nghĩa trong test |
| --- | --- |
| `response.statusCode()` | Phản hồi thực tế 200, 302, 404, 407… |
| `response.headers()` | Kiểm tra `Location`, `Set-Cookie` hoặc header do fixture đặt |
| `response.uri()` | URI của response; có thể là URI đích cuối nếu đã redirect |
| `response.request()` | Request tương ứng với response này; sau redirect có thể là request **đã được chuyển hướng**, không phải ban đầu |
| `response.previousResponse()` | Có thể chứa các response trung gian do redirect/xác thực |
| `response.body()` | Dữ liệu theo `BodyHandler<T>` đã chọn |
| `response.version()` | HTTP version thực sự được sử dụng |

Khi `response.previousResponse().isPresent()`, **body của intermediate response do `previousResponse()` trả về là `null`** theo hợp đồng `HttpResponse`. Không cố parse body của những response này như payload ứng dụng.

## 3. Kiểm thử proxy: kiểm tra đường đi chứ không chỉ kiểm tra builder

### Cấu hình một HTTP proxy tường minh

~~~java
ProxySelector selector = ProxySelector.of(
        new InetSocketAddress("127.0.0.1", 8888));

HttpClient client = HttpClient.newBuilder()
        .proxy(selector)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

Đây là **mã minh họa**, cần import `java.net.ProxySelector`/`InetSocketAddress` và `HttpClient`/`Duration`. Cổng `8888` chỉ hợp lệ khi có proxy đang lắng nghe; đừng dùng nguyên số này mà không có fixture.

`ProxySelector.of(address)` cung cấp một selector cố định chọn proxy. Trong môi trường phức tạp hơn, một `ProxySelector` tùy biến có thể chọn proxy hoặc kết nối trực tiếp theo `URI`, hostname và scheme. `HttpClient.Builder.NO_PROXY` là selector tiện ích luôn trả `Proxy.NO_PROXY` để yêu cầu kết nối trực tiếp.

**Không nên đặt các thuộc tính proxy toàn cục trong một unit test dùng chung JVM** như `System.setProperty("http.proxyHost", ...)` hoặc `ProxySelector.setDefault(...)` nếu bài kiểm thử chỉ định cấu hình một client. Thay đổi toàn cục có thể ảnh hưởng test chạy song song và tạo phụ thuộc môi trường khó tái hiện.

### Phân biệt HTTP proxy thường với HTTPS CONNECT

Với request **HTTP** thông thường qua forward proxy, client có thể gửi đường dẫn ở dạng **absolute-form request target** như:

~~~http
GET http://example.invalid/demo HTTP/1.1
Host: example.invalid
~~~

Đây là **minh họa giao thức**, không phải lời gọi Java. Proxy nhận URI đích rồi có thể chuyển tiếp yêu cầu. Trong Java 11, một HTTP server fixture đơn giản có thể đóng vai **proxy giả lập**: nhận request và trả phản hồi xác định, nhưng **không chuyển tiếp** lên origin. Điều đó đủ để kiểm tra “request đã đi tới proxy” mà không đòi hỏi mạng bên ngoài.

Với **HTTPS** qua HTTP proxy, thông thường có bước `CONNECT` tạo tunnel đến server đích rồi thực hiện TLS trên tunnel. Một fixture chỉ trả lời GET không đủ để kiểm chứng đầy đủ proxy HTTPS, TLS trust, chứng chỉ hay hostname verification. Khi cần kiểm thử HTTPS proxy, dùng một proxy fixture hỗ trợ `CONNECT` và TLS test server có chứng chỉ hợp lệ cho môi trường test; **không vô hiệu hóa certificate validation** để “làm cho test chạy”.

### Điều kiện PASS của test proxy

- Fixture proxy thực sự **nhận được** request gửi tới một URI giả định, không phải chỉ có `client.proxy().isPresent() == true`.
- Response trả về từ proxy có status/body/header sentinel mà origin không thể tạo.
- Khi client dùng `NO_PROXY`, request đến trực tiếp origin fixture, không vô tình lệ thuộc proxy hệ thống.
- Test dùng cổng động `0` của hệ điều hành, tránh tranh cổng 8080/8888 với app khác.
- Khi proxy báo lỗi hoặc bị từ chối kết nối, code quan sát được loại lỗi/status tương ứng, không tự coi mọi `IOException` là “proxy timeout”.

**Trạng thái `407 Proxy Authentication Required`** là response do proxy phát ra; khác `401 Unauthorized` do server đích phát ra. Nếu có authenticator, thử tách riêng chính sách credentials cho proxy và server; không ghi username/password vào log.

## 4. Kiểm thử redirect: `NEVER`, `NORMAL` và `ALWAYS`

Java 11 cung cấp enum:

~~~java
HttpClient.Redirect.NEVER
HttpClient.Redirect.NORMAL
HttpClient.Redirect.ALWAYS
~~~

Policy đặt trên `HttpClient.Builder.followRedirects(policy)`:

| Policy | Ý nghĩa | Khi nào thích hợp |
| --- | --- | --- |
| `NEVER` | Không tự động theo redirect | Muốn tự kiểm tra 3xx/`Location` và kiểm soát đích |
| `NORMAL` | Tự theo redirect, **ngoại trừ HTTPS sang HTTP** | Cần hỗ trợ redirect thông thường mà không hạ từ HTTPS xuống HTTP |
| `ALWAYS` | Cho phép theo redirect kể cả HTTPS sang HTTP theo policy | Chỉ khi có lý do rõ ràng và kiểm soát rủi ro downgrade |

**Mặc định của `HttpClient` là `Redirect.NEVER`** nếu builder không chỉ định policy. Mã ứng dụng muốn theo redirect cần cấu hình tường minh.

### Cách test deterministic cho 302

Fixture origin cung cấp:

~~~text
GET /redirect
    -> HTTP 302
    -> Location: /final

GET /final
    -> HTTP 200
    -> body: final-body
~~~

Với `NEVER`, test mong đợi `statusCode() == 302` và `headers().firstValue("Location")` là `/final`; không có lý do phải liên hệ `/final`. Với `NORMAL`, test mong đợi HTTP 200, `response.uri().getPath().equals("/final")` và `previousResponse().get().statusCode() == 302`.

Kiểm tra trung gian:

~~~java
HttpResponse<String> followed = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

int finalStatus = followed.statusCode();
URI finalUri = followed.uri();
int originalRedirectStatus =
        followed.previousResponse().orElseThrow().statusCode();
~~~

**Mã minh họa**: giả định client cấu hình `Redirect.NORMAL`, request đến fixture redirect, xử lý checked exceptions. `previousResponse()` có thể là `Optional.empty()` nếu không có redirect/authentication, không được `get()` mù quáng trong trường hợp chung.

### Redirect có thể thay đổi method

Không áp đặt rằng HTTP method luôn giữ nguyên khi chuyển hướng. Theo tài liệu `HttpClient.Redirect` Java 11, **301/302 có thể chuyển POST thành GET**; `303` cũng có semantics chuyển sang truy xuất tài nguyên khác. Ngược lại `307/308` được thiết kế nhằm giữ method/body theo HTTP semantics, nhưng khả năng lặp lại body còn phụ thuộc `BodyPublisher`. Vì vậy, khi test một API POST quan trọng, **kiểm tra method và body tại origin đích** thay vì chỉ kiểm tra mã cuối cùng 200.

Nếu server tạo redirect loop, chuỗi dài hoặc Location không hợp lệ, client có thể ngừng theo và trả status/lỗi tùy hợp đồng/implementation; test cần có timeout và **không giả định policy `ALWAYS` nghĩa là theo vô hạn**.

### Bảo mật redirect

- **Cross-origin redirect:** từ host A sang host B có thể làm thay đổi nơi nhận request. Kiểm tra `response.uri()` và whitelist host/scheme nếu URL có thể không tin cậy.
- **HTTPS → HTTP:** `NORMAL` không tự theo downgrade; `ALWAYS` có thể cho phép, nhưng điều đó không an toàn cho thông tin bí mật trên mạng.
- **Credentials:** không giả định mọi bản triển khai tự loại/bảo toàn `Authorization`, Cookie header hoặc token tùy biến theo cách phù hợp cho ứng dụng. Kiểm thử không rò rỉ credentials khi redirect qua host khác.
- **SSRF:** nếu ứng dụng cho phép gọi URL từ input ngoài, redirect có thể chuyển tới tài nguyên nội bộ. Cần kiểm soát cả **mọi đích được chuyển hướng**, không chỉ URI ban đầu.
- **Open redirect:** một endpoint được tin cậy vẫn có thể gửi `Location` đến host không đáng tin; policy auto redirect không thay thế quy tắc an ninh.
- **Body size:** một server lỗi có thể trả body lớn khi 3xx/4xx; chọn body handler và giới hạn kích thước phù hợp.

## 5. “Phiên độc lập” nghĩa là gì khi dùng `HttpClient`?

HTTP bản chất không buộc client phải có một “login session object”. Server có thể dùng cookie `Set-Cookie`/`Cookie`, bearer token, mTLS hoặc cơ chế riêng để nhận biết client. `HttpClient` **không tự cấp một phiên đăng nhập ứng dụng**.

Để kiểm thử session cookie tách biệt, Java cung cấp:

~~~java
CookieManager cookieJarA = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
CookieManager cookieJarB = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient clientA = HttpClient.newBuilder()
        .cookieHandler(cookieJarA)
        .proxy(HttpClient.Builder.NO_PROXY)
        .build();

HttpClient clientB = HttpClient.newBuilder()
        .cookieHandler(cookieJarB)
        .proxy(HttpClient.Builder.NO_PROXY)
        .build();
~~~

**Đoạn code minh họa**, cần import `java.net.CookieManager`/`CookiePolicy` và `HttpClient`.

Ở đây có **hai `CookieManager` độc lập**. Vì `CookieManager(null, policy)` tự tạo `CookieStore` in-memory khi store là `null`, cookie từ response của A có thể được lưu trong jar A mà **không tự xuất hiện trong jar B**. Policy `ACCEPT_ORIGINAL_SERVER` chỉ nhận cookie theo điều kiện server-origin tương ứng, hợp lý hơn `ACCEPT_ALL` cho nhiều tình huống.

### Test cookie đi qua HTTP thực tế

Fixture cung cấp:

~~~text
Client A: GET /login
Server:   Set-Cookie: SID=alpha; Path=/; HttpOnly

Client A: GET /whoami
Server:   echo Cookie header
Expected: SID=alpha

Client B: GET /whoami
Server:   echo Cookie header
Expected: none
~~~

Cách test này mạnh hơn chỉ gọi `cookieJarA.getCookieStore().getCookies()`, vì nó xác nhận **cookie thực sự được gửi trong request** tới đúng origin/path. Với cookie có `Secure`, cần HTTPS; ví dụ ở phần 7 dùng HTTP loopback nên chủ ý **không** đặt `Secure` và chỉ nhằm kiểm thử logic, không phải cấu hình cookie production.

### Những điểm dễ khiến hai phiên bị lẫn

| Tình huống | Có cách ly session không? |
| --- | --- |
| Mỗi `HttpClient` nhận **một `CookieManager` riêng** | Cookie jar có thể cách ly nếu không có trạng thái chung khác |
| Hai `HttpClient` cùng dùng **một `CookieManager`** | **Không** cách ly cookie; cả hai tham chiếu cùng jar |
| Mỗi client có jar riêng, nhưng dùng chung token từ biến toàn cục | **Không** cách ly token |
| Không đặt `cookieHandler`, nhưng tự thêm cùng `Cookie` header trên mọi request | **Không** cách ly thủ công |
| Chỉ tạo hai `HttpRequest` khác nhau, gửi qua một client có cùng jar | Mọi request có thể dùng chung session của jar |
| Dùng chung `Authenticator` mutable chứa credential thay đổi | Có nguy cơ lẫn danh tính nếu không đồng bộ/thiết kế đúng |
| Dùng chung proxy nhưng mỗi client có jar riêng | Chia sẻ proxy **không tự** làm jar bị chia sẻ; nhưng proxy/server có thể có trạng thái/ghi log riêng |
| Cùng DNS/IP/HTTP connection pool nhưng cookie riêng | Không suy ra cookie leak chỉ từ việc trùng host/IP; cần xem cookie/token thực gửi |

**Isolation boundary nằm ở toàn bộ identity context**, không chỉ ở tên biến client. Nếu hệ thống phục vụ nhiều tenant/người dùng, cần thiết kế ownership riêng cho cookie jar, token provider, authentication, request headers và logging. Không để một `CookieManager` hoặc HTTP client chứa credential của người A bị tái sử dụng cho người B.

### Session độc lập không đồng nghĩa connection độc lập hoàn toàn

Một `HttpClient` có thể quản lý các kết nối trong nội bộ và tái sử dụng chúng; đó là tối ưu HTTP transport. Hai `HttpClient` mới có cấu hình độc lập, nhưng phạm vi pooling/tài nguyên cụ thể phụ thuộc implementation. **Cookie session** là lớp dữ liệu khác: nó được xác định bởi các cookies/headers và logic server, không phải mỗi socket một session.

Không dựa vào ephemeral port, TCP connection ID hay địa chỉ IP để xác nhận hai người dùng có tách session. **Quan sát HTTP header thực gửi và trạng thái server** mới là test mục tiêu.

### Test đầy đủ hơn cho cookie

Ngoài ví dụ đăng nhập đơn giản, với hệ thống thật cần kiểm thử `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, expiry, logout và policy của `CookieHandler` phù hợp theo yêu cầu ứng dụng. Không giả định Java `HttpClient` có hành vi giống hoàn toàn browser về mọi chính sách cookie hiện đại; một server có session cần được kiểm tra bằng đúng client/runtime đang dùng.

Không log giá trị cookie/session ID thật, không gửi token thật tới proxy fixture và không dùng URL có userinfo để “mô phỏng” credential trong log.

## 6. Chuẩn bị test fixture: origin server và proxy giả lập

Một bài test tốt có thể thiết kế hai server chạy trên `127.0.0.1` và **cổng động**:

| Fixture | Endpoint | Hành vi cố định |
| --- | --- | --- |
| Origin | `/redirect` | Trả 302 và `Location: /final` |
| Origin | `/final` | Trả 200, body `final-body` |
| Origin | `/login` | Trả `Set-Cookie: SID=alpha; Path=/; HttpOnly` |
| Origin | `/whoami` | Echo request `Cookie` nếu có; nếu không trả `none` |
| Proxy stub | `/` | Nhận request dạng absolute-form và trả sentinel; **không chuyển tiếp** tới origin |

Cần ghi rõ tính chất của proxy stub:

- Đây **không phải một forward proxy hoàn chỉnh**; chỉ dùng chứng minh `HttpClient` gửi request đến địa chỉ proxy khi được cấu hình.
- Test HTTP proxy thực sự thường kiểm tra **request-target absolute-form** cho HTTP, và test HTTPS phải xử lý `CONNECT`/TLS.
- Không dùng một hostname Internet thật cho request đích của proxy stub. Ví dụ dùng `test-target.invalid` thuộc vùng `.invalid`, proxy stub chỉ trả response cục bộ. Bản demo không có lý do liên hệ Internet để tìm website.
- Các kết quả không phụ thuộc thứ tự request giữa nhiều thread vì phần kiểm chứng cơ bản dùng những `client.send` tuần tự, không tạo request song song đến cùng endpoint.

**Không khởi chạy server trong test mà quên `stop(0)` ở `finally`.** Nếu không dọn fixture, các phép thử có thể giữ socket mở, gây leak hoặc làm CI treo.

## 7. Ví dụ Java 11 hoàn chỉnh: kiểm thử cả ba hành vi

Chương trình này **không dùng thư viện ngoài**, chỉ Java SE HTTP Client và module `jdk.httpserver` có trong JDK đầy đủ. Nó kiểm tra redirect `NEVER/NORMAL`, hai cookie jar độc lập và HTTP proxy stub. Dữ liệu cookie `SID=alpha` chỉ là giá trị giả trong demo trên loopback.

Tạo tệp **HttpConfigIsolationDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpConfigIsolationDemo {
    public static void main(String[] args) throws Exception {
        HttpServer origin = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        HttpServer proxy = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        origin.createContext("/redirect", exchange -> {
            exchange.getResponseHeaders().set("Location", "/final");
            exchange.sendResponseHeaders(302, -1);
            exchange.close();
        });
        origin.createContext("/final",
                exchange -> reply(exchange, 200, "final-body"));
        origin.createContext("/login", exchange -> {
            exchange.getResponseHeaders().set(
                    "Set-Cookie", "SID=alpha; Path=/; HttpOnly");
            reply(exchange, 200, "logged-in");
        });
        origin.createContext("/whoami", exchange -> {
            String cookie = exchange.getRequestHeaders().getFirst("Cookie");
            reply(exchange, 200, cookie == null ? "none" : cookie);
        });
        proxy.createContext("/", exchange -> {
            boolean absoluteForm = exchange.getRequestURI().isAbsolute();
            reply(exchange, 200, absoluteForm
                    ? "proxy-received-absolute-uri" : "proxy-received-relative-uri");
        });

        origin.start();
        proxy.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + origin.getAddress().getPort() + "/");
            HttpClient noRedirect = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .build();
            HttpClient followRedirect = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .build();

            HttpRequest redirect = get(base.resolve("redirect"));
            HttpResponse<String> raw = noRedirect.send(redirect,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            HttpResponse<String> followed = followRedirect.send(redirect,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("neverStatus=" + raw.statusCode());
            System.out.println("neverLocation=" +
                    raw.headers().firstValue("Location").orElse("missing"));
            System.out.println("normalStatus=" + followed.statusCode());
            System.out.println("normalPath=" + followed.uri().getPath());
            System.out.println("previousStatus=" +
                    followed.previousResponse().orElseThrow().statusCode());
            System.out.println("previousBodyIsNull=" +
                    (followed.previousResponse().orElseThrow().body() == null));

            CookieManager jarA = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            CookieManager jarB = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            HttpClient sessionA = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .cookieHandler(jarA).build();
            HttpClient sessionB = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .cookieHandler(jarB).build();

            sessionA.send(get(base.resolve("login")),
                    HttpResponse.BodyHandlers.discarding());
            String cookieA = sessionA.send(get(base.resolve("whoami")),
                    HttpResponse.BodyHandlers.ofString()).body();
            String cookieB = sessionB.send(get(base.resolve("whoami")),
                    HttpResponse.BodyHandlers.ofString()).body();
            System.out.println("sessionACookie=" + cookieA);
            System.out.println("sessionBCookie=" + cookieB);
            System.out.println("jarsDistinct=" + (jarA != jarB));

            HttpClient viaProxy = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .proxy(ProxySelector.of(
                            new InetSocketAddress("127.0.0.1",
                                    proxy.getAddress().getPort())))
                    .build();
            HttpResponse<String> proxyReply = viaProxy.send(
                    get(URI.create("http://test-target.invalid/probe")),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("proxyStatus=" + proxyReply.statusCode());
            System.out.println("proxyBody=" + proxyReply.body());
            System.out.println("proxyConfigured=" + viaProxy.proxy().isPresent());
        } finally {
            origin.stop(0);
            proxy.stop(0);
        }
    }

    private static HttpRequest get(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5)).GET().build();
    }

    private static void reply(HttpExchange exchange, int status,
                              String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        try {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }
}
~~~

Biên dịch và chạy trên JDK có module `jdk.httpserver`. `--release 11` ép sử dụng API/cú pháp hỗ trợ ở Java 11 ngay cả khi test trên JDK mới:

~~~bash
javac --release 11 --add-modules jdk.httpserver HttpConfigIsolationDemo.java
java --add-modules jdk.httpserver HttpConfigIsolationDemo
~~~

**Stdout đã kiểm chứng** (JDK 24, compile `--release 11`):

~~~text
neverStatus=302
neverLocation=/final
normalStatus=200
normalPath=/final
previousStatus=302
previousBodyIsNull=true
sessionACookie=SID=alpha
sessionBCookie=none
jarsDistinct=true
proxyStatus=200
proxyBody=proxy-received-absolute-uri
proxyConfigured=true
~~~

### Giải thích từng nhóm kết quả

**Nhóm redirect:**

- `neverStatus=302` và `neverLocation=/final` chứng tỏ policy `NEVER` giữ response redirect ở caller, không tự gửi request GET tiếp theo tới `/final`.
- `normalStatus=200`, `normalPath=/final` chứng tỏ client `NORMAL` đã tự gửi request tới URI đích, sau đó nhận response cuối.
- `previousStatus=302` và `previousBodyIsNull=true` chứng minh client ghi nhận response trung gian; body của `previousResponse()` không sẵn để đọc lại theo hợp đồng API.

**Nhóm phiên độc lập:**

- `sessionACookie=SID=alpha`: request `/login` nhận `Set-Cookie`, `CookieManager A` lưu cookie; lần GET `/whoami` của A gửi header `Cookie` tương ứng.
- `sessionBCookie=none`: client B dùng `CookieManager B` chưa đăng nhập; server nhận request không có `Cookie`. Đây là điều kiện **isolation ở tầng HTTP** mà test cần quan sát.
- `jarsDistinct=true`: hai client thực sự được cấu hình với hai object jar khác nhau. Chỉ kiểm tra identity jar chưa đủ, nhưng kết hợp với kết quả server nhận thì có bằng chứng tốt.

**Nhóm proxy:**

- `proxyStatus=200` và `proxyBody=proxy-received-absolute-uri` xác nhận proxy stub ở loopback nhận được request HTTP với URI tuyệt đối.
- `proxyConfigured=true` xác nhận client `viaProxy` có selector tường minh. **Hai kiểm tra kết hợp** mới xác nhận hành vi route; `isPresent()` một mình không đủ.
- Host `test-target.invalid` không có server thực sự. **Proxy stub không forward** đến host này; vì vậy output chỉ chứng minh routing qua HTTP proxy và absolute request-target, không chứng minh khả năng CONNECT, xác thực proxy hay forward HTTP tới destination thật.

Chương trình luôn dừng cả hai HTTP server trong `finally`. Các client được tạo với JDK HTTP Client Java 11, không đưa vào `try-with-resources` bởi `HttpClient` ở Java 11 chưa triển khai `AutoCloseable`; các phiên bản Java mới có thêm API quản lý vòng đời. Với ứng dụng lớn, cần quản lý client, thread/executor, body streams và resource ownership theo thời điểm dừng phù hợp.

## 8. Từ demo stdout sang kiểm thử tự động có assertions

Khi dùng JUnit hoặc framework test, nên thay `System.out.println` bằng những assertion trên **giá trị nhận được và dấu vết ở fixture**, thay vì kiểm tra log chữ. Ví dụ:

~~~java
if (raw.statusCode() != 302) {
    throw new AssertionError("NEVER must expose 302");
}
if (followed.statusCode() != 200
        || !"/final".equals(followed.uri().getPath())) {
    throw new AssertionError("NORMAL must reach /final");
}
if (!"SID=alpha".equals(cookieA) || !"none".equals(cookieB)) {
    throw new AssertionError("Cookie jars are not isolated");
}
if (!"proxy-received-absolute-uri".equals(proxyReply.body())) {
    throw new AssertionError("Proxy was not used");
}
~~~

Đây là **mã minh họa để chèn sau các biến ở chương trình đầy đủ**; không độc lập và không phải ví dụ tạo fixture mới. Tăng chất lượng test bằng cách ghi đếm request ở từng server/endpoint:

- `NEVER`: fixture `/final` không được gọi do redirect này.
- `NORMAL`: fixture `/final` nhận đúng lần chuyển hướng mong đợi.
- `NO_PROXY`: origin nhận request trực tiếp, proxy không nhận request của client đó.
- `viaProxy`: proxy nhận request có absolute URI. Nếu proxy được thiết kế forward thật, origin cũng cần nhận request forwarded; stub trong ví dụ cố tình không forward.
- Phiên A và B: request `/whoami` có/không có cookie đúng với định danh client. Đừng chỉ kiểm tra sự tồn tại của một `Cookie` trong CookieStore.

### Một ma trận kiểm thử cơ bản

| Test case | Setup | Expected |
| --- | --- | --- |
| Redirect off | `Redirect.NEVER`, origin trả 302 + Location | Response giữ 302; caller tự thấy `Location` |
| Redirect on | `Redirect.NORMAL`, /redirect → /final | Response 200, final URI là /final, previous response 302 |
| Redirect HTTPS downgrade | HTTPS URL redirect sang HTTP | `NORMAL` không tự theo downgrade |
| Redirect loop | A → B → A | Không theo vô hạn; test bounded timeout và chính sách ứng dụng |
| POST 302 | Origin trả 302 | Kiểm tra method/body đích theo Java 11 Redirect semantics, không giả định còn POST |
| Proxy off | `HttpClient.Builder.NO_PROXY` | Origin nhận trực tiếp, stub proxy không nhận |
| Proxy on | `ProxySelector.of(localProxyAddress)` | Stub nhận absolute-form HTTP request |
| Proxy unavailable | Proxy cố ý từ chối/đóng kết nối | Kết quả lỗi transport phù hợp, không đoán luôn timeout |
| Proxy 407 | Stub trả 407 | Kiểm tra status và policy xử lý xác thực proxy |
| Session A logged in | A nhận Set-Cookie từ /login | A gửi SID đúng khi gọi /whoami |
| Session B fresh | B có CookieManager riêng | B không gửi SID của A |
| Shared-jar negative test | A và B cấu hình chung một CookieManager | Chứng minh nguy cơ dùng chung state |
| Cookie path/domain | Set-Cookie chỉ cho path/host cụ thể | Chỉ request phù hợp mang cookie |
| Cross-origin redirect | Chuyển sang host khác | Không rò rỉ Authorization/token ngoài policy |
| Concurrency | Nhiều tenant/request đồng thời | Không cross-contamination state giữa các identity context |

Ma trận này là **kế hoạch kiểm thử mở rộng**, không tuyên bố tất cả case đã được chương trình ngắn ở phần 7 chạy. Một số case cần HTTPS test certificate, fake proxy có khả năng CONNECT, nhiều origin fixture hoặc automation chuyên dụng.

## 9. Kiểm thử nâng cao: các tình huống có thể làm lộ lỗi thật

### 9.1 Redirect giữa các hostname / scheme

Một redirect 302 cùng origin khá đơn giản. Lỗi bảo mật thường xuất hiện khi chuyển sang origin khác, thậm chí HTTPS → HTTP hoặc tới tài nguyên mạng nội bộ.

Khi test redirect chéo origin, nên khởi tạo **hai origin servers** (hoặc hostnames cục bộ ánh xạ thích hợp). Fixture A trả `Location` trỏ sang B. Fixture B ghi lại:

- Request method và URL đã tới.
- Các header nhạy cảm như `Authorization`/`Cookie` có được gửi không; **chỉ ghi boolean/giá trị giả**, không in token thật.
- Host/Scheme theo đường đi, không chỉ final HTTP status.

Ứng dụng có thể cần chính sách chặn redirect ngoài allowlist. Nếu sử dụng `Redirect.NEVER` và tự follow bằng code, hãy kiểm soát số hop, scheme, domain/IP, chuyển hướng tới localhost và method/body khi dựng request mới. Test chỉ làm việc với `https://` khi có TLS server/certificate đúng, không tự tắt hostname verification.

### 9.2 Redirect với request body không thể phát lại

BodyPublisher được tạo từ một `InputStream` dùng một lần có thể không phù hợp cho việc phát lại khi redirect/authentication challenge. Để test POST có body, đừng chỉ dựa vào status 200 cuối cùng: origin đích phải xác nhận nội dung và method đúng hợp đồng.

Bài test cần dựa trên **HTTP semantics của method/status** và hành vi Java HTTP Client được công bố, thay vì kỳ vọng mọi 301/302/307/308 được xử lý giống nhau. Với API có side effect, tự động redirect/retry còn có nguy cơ lặp thao tác ở server; cân nhắc `Redirect.NEVER` hoặc quy tắc rõ hơn.

### 9.3 HTTP proxy dùng xác thực

Một proxy thật có thể yêu cầu `Proxy-Authorization` hoặc phản hồi 407; server đích có thể trả 401. Java `HttpClient.Builder.authenticator(...)` là nơi cung cấp `Authenticator`, nhưng tránh đặt chung credentials server và proxy thiếu kiểm soát. Test:

1. Proxy từ chối request không có credential.
2. Proxy chấp nhận credential test hợp lệ.
3. Credential của origin không xuất hiện trong request tới một host khác ngoài ý muốn.
4. Failed authentication không tạo vòng retry vô hạn.
5. Secret không bị log.

Không hardcode mật khẩu production vào source/test fixture; dùng giá trị giả hoặc inject qua môi trường test được kiểm soát.

### 9.4 Cookie jar chung làm hỏng isolation

Bài kiểm thử âm rất hữu ích:

~~~java
CookieManager shared = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient first = HttpClient.newBuilder()
        .cookieHandler(shared).build();

HttpClient second = HttpClient.newBuilder()
        .cookieHandler(shared).build();
~~~

**Mã minh họa**, cần imports và endpoint HTTP thật để test. Hai client ở đây khác object, nhưng trỏ vào **cùng `CookieManager`**. Một cookie do first lưu có thể được gửi bởi second nếu URI/path/domain đáp ứng điều kiện cookie. Vì vậy, **client object identity không phải cơ chế cô lập session**. Nếu hệ thống đa tenant, hãy xem luôn nơi giữ token provider, header được copy, bearer credential và cookie store.

### 9.5 Cookie hết hạn/logout và session phía server

Cookie ở client chỉ là một phần session. Khi server logout/invalidate session, client có thể vẫn giữ cookie cũ nhưng server không còn công nhận giá trị đó. Ngược lại, xóa CookieStore không thay thế cơ chế invalidate phía server khi bảo mật yêu cầu.

Test nên kiểm tra end-to-end: login, cookie được gửi, server nhận biết user; logout, cookie mới/xóa cookie được xử lý; request kế tiếp không còn được ủy quyền. Không nhầm “cookie được gửi” với “được đăng nhập thành công” trong mọi hệ thống.

### 9.6 Test đồng thời nhiều client

Nếu tạo hàng trăm request song song, không nên kiểm tra session qua một static mutable `currentCookie` hoặc biến `activeUser`. Mỗi request phải mang identity context riêng và mọi callback xử lý an toàn. Dùng `sendAsync(...)` có thể giúp tạo tải kiểm thử, nhưng cần chờ **tất cả futures hoàn tất** và xác minh từng response thuộc đúng client/tenant.

Khi test thay đổi proxy selector hoặc cookie store trong lúc request đang chạy, phải hiểu thread-safety của implementation. Để test cấu hình bất biến, tạo client mới với selector/jar mới; đừng sửa một biến toàn cục và kỳ vọng client đã build tự nhận cấu hình.

## 10. Những dấu hiệu test yếu và cách sửa

| Dấu hiệu | Vì sao chưa đủ | Test tốt hơn |
| --- | --- | --- |
| Chỉ gọi `client.proxy().isPresent()` | Không xác nhận đường đi request | Stub proxy ghi request thực tế |
| Dựa vào `ProxySelector.setDefault` | Phụ thuộc môi trường, gây ảnh hưởng test khác | Mỗi client có selector tường minh |
| Dùng proxy công cộng/production trong test | Mạng và dịch vụ biến động, có thể lộ dữ liệu | Proxy fixture trên loopback |
| Tạo redirect URL Internet thật | Không deterministic | Origin fixture trả 302 có Location cố định |
| Chỉ assert final status 200 | Không xác nhận redirect đã xảy ra hay không | Kiểm tra final URI, previous response và request count |
| Giả định mọi 3xx đều được follow | Còn policy, method và Location | Assert theo response status/URI và policy |
| Dùng chung CookieManager rồi bảo “hai phiên” | Cookie state chung | Tạo jar khác nhau, kiểm HTTP Cookie header |
| Chỉ assert jarA != jarB | Chưa kiểm tra cookie có được gửi đúng | Server echo Cookie từng client |
| Tạo Cookie jar riêng nhưng copy token chung | Identity context vẫn bị lẫn | Kiểm cả token, Authenticator, headers |
| Dùng body của `previousResponse()` | Intermediate body được trả null | Kiểm status/headers/URI thay thế |
| Gọi proxy stub nhưng mong origin đã nhận | Stub không forward | Nêu rõ phạm vi hoặc dùng forward proxy thật |
| Dùng `Redirect.ALWAYS` cho URL bất kỳ | Có nguy cơ downgrade/SSRF | Áp policy/allowlist và kiểm đích |
| Vô hiệu hóa TLS verify khi test HTTPS | Ẩn lỗi chứng chỉ quan trọng | Local CA/test certificate đúng |
| Hardcode cổng | CI có thể bị chiếm cổng | `InetSocketAddress("127.0.0.1", 0)` |
| Không stop server | Leak socket, test suite treo | `try/finally` với `stop(0)` |
| In cookie/token thật vào log | Rò rỉ thông tin | Dùng giá trị giả, assert boolean/ID đã lọc |
| Giả định một `IOException` là proxy timeout | Có nhiều lỗi mạng khác nhau | Phân loại exception/status theo API |
| Test chỉ trên một JDK | Có khác biệt provider/chính sách | Kiểm thử mục tiêu Java 11+ và JDK deployment |

## 11. Checklist triển khai kiểm thử trong dự án

### Thiết lập

- [ ] Dùng **Java 11+** với `java.net.http`; không phụ thuộc HTTP Client incubator đã cũ.
- [ ] Khởi động fixture origin/proxy trên `127.0.0.1` và cổng `0` để hệ điều hành chọn cổng.
- [ ] Khai báo test timeout hữu hạn bằng `HttpRequest.Builder.timeout(Duration)` để lỗi không treo vô hạn.
- [ ] Cấu hình `HttpClient.Builder.NO_PROXY` cho test direct; không phụ thuộc proxy máy dev/CI.
- [ ] Chỉ dùng URL/tên miền giả và cookie/token giả khi test, không liên hệ môi trường production.

### Proxy

- [ ] Với HTTP proxy stub, kiểm tra **proxy thực sự đã nhận** request absolute-form.
- [ ] Với HTTPS qua proxy, dùng test fixture hỗ trợ CONNECT/TLS thay vì giả định HTTP stub đủ.
- [ ] Kiểm tra status 407 / proxy unavailable và cách báo lỗi.
- [ ] Nếu proxy có credential, không trộn secret của origin và proxy.

### Redirect

- [ ] Kiểm `NEVER` nhận 302/`Location`.
- [ ] Kiểm `NORMAL` nhận status/URI cuối cùng và `previousResponse()`.
- [ ] Nếu theo redirect tự động, kiểm thêm method/body và số lần hop theo hợp đồng.
- [ ] Kiểm cross-origin/HTTPS downgrade bằng môi trường thích hợp.
- [ ] Không cho redirect mở rộng phạm vi truy cập nội bộ ngoài allowlist.

### Phiên

- [ ] CookieManager/CookieStore khác nhau cho identity context cần cách ly.
- [ ] Test A login, B chưa login; kiểm server nhận `Cookie` chỉ từ A.
- [ ] Không dùng chung token provider mutable/Auth header hoặc `Authenticator` sai phạm vi.
- [ ] Test cookie domain/path/secure/expiry/logout với server fixture có trạng thái.
- [ ] Không in cookie thật trong stdout/log.

### Dọn dẹp và quan sát

- [ ] Kiểm body response được tiêu thụ/đóng theo handler thích hợp.
- [ ] Dừng toàn bộ HTTP server/test proxy trong `finally`.
- [ ] Nếu chạy nhiều request async, đợi kết quả và cleanup mọi future/stream.
- [ ] Đo đạc kết quả theo request ID/test case, không nhầm request tới origin với request qua proxy.
- [ ] Chỉ coi QA PASS khi có **assertion trên hành vi mạng quan sát được**, không chỉ kiểm object đã cấu hình.

**Ghi nhớ:** Cấu hình proxy, redirect và cookie ở `HttpClient` phải được kiểm thử tại **đường đi HTTP thực sự**. Dùng origin/proxy fixture trên loopback, xác minh status/`Location`/final URI, và dùng cookie jar độc lập để tránh lẫn phiên. Các API này là **Java 11 chuẩn và tiếp tục hiện hành**.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 11 — `HttpClient`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): client per-instance configuration, `proxy()`, `cookieHandler()`, `followRedirects()`, default redirect.
- [Oracle Java SE 11 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `proxy(ProxySelector)`, `NO_PROXY`, `cookieHandler(CookieHandler)`, `followRedirects(Redirect)`.
- [Oracle Java SE 11 — `HttpClient.Redirect`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html): `NEVER`/`NORMAL`/`ALWAYS`, downgrade và thay đổi method khi redirect.
- [Oracle Java SE 11 — `HttpResponse<T>`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `uri()`, `request()`, `previousResponse()`, body của intermediate response.
- [Oracle Java SE 11 — `ProxySelector`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/ProxySelector.html): `of(InetSocketAddress)`, proxy selection và default selector.
- [Oracle Java SE 11 — `CookieManager`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/CookieManager.html): CookieHandler, CookieStore và chính sách nhận cookie.
- [Oracle Java SE 11 — `CookiePolicy`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/CookiePolicy.html): `ACCEPT_ORIGINAL_SERVER` và các chính sách cookie.
- [Oracle Java SE 11 — module `jdk.httpserver`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/module-summary.html): fixture `HttpServer` cho integration test không cần thư viện ngoài.
- [Oracle Java SE 25 — `HttpClient`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): các API HTTP Client vẫn được hỗ trợ; có bổ sung quản lý vòng đời ở JDK mới.
- [Oracle Java SE 25 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): cấu hình proxy, redirect, cookie hiện hành.

Bài học chỉ dùng API được hỗ trợ từ Java 11 trở đi. Không dùng `jdk.incubator.httpclient` hoặc kỹ thuật legacy, không khẳng định proxy stub là proxy HTTPS hoàn chỉnh và không giả định tạo hai object `HttpClient` đủ để cô lập mọi credential.