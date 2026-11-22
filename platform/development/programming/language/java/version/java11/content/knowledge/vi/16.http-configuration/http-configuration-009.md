# Chính sách header, cookie khi đi qua nhiều đích — Java 11+

## Mục tiêu và phạm vi

Một ứng dụng Java HTTP Client có thể gọi nhiều endpoint: API chính, dịch vụ xác thực, CDN tải tệp, đối tác bên ngoài, hoặc URL được trả về trong `Location` của HTTP redirect. Nếu sao chép toàn bộ header từ đích A sang đích B, ứng dụng có thể làm lộ **bearer token, API key, cookie phiên và dữ liệu riêng của tenant**. Ngược lại, nếu không quản lý cookie đúng, một client dùng chung có thể gửi session cookie sang một endpoint mà lập trình viên nghĩ là đã được tách biệt.

Từ Java 11, `java.net.http.HttpClient` là API chuẩn, có cấu hình redirect qua `HttpClient.Builder.followRedirects(...)` và cookie qua `HttpClient.Builder.cookieHandler(...)`. Các API này vẫn hiện hành trong Java hiện đại. Bài học làm rõ:

1. **Origin**: scheme, host và port; là một ranh giới tin cậy hữu ích khi quyết định có được gửi credential sang một URI mới.
2. **Cookie scope**: host/domain, path, secure và thuộc tính liên quan; **không tương đương origin**, đặc biệt không phân tách theo TCP port.
3. **Header policy**: header được xác định **cho từng HttpRequest**, không chuyển nguyên `Authorization`, `Cookie` hoặc API key khi theo redirect.
4. **Redirect policy**: phân biệt `NEVER`, `NORMAL`, `ALWAYS` và kiểm tra từng hop khi có thông tin nhạy cảm.
5. **CookieManager/CookieStore**: nhận, lưu và gửi cookies trong phạm vi client và tenant phù hợp.
6. Thực hành bằng **hai HTTP server loopback** trên hai cổng khác nhau, biên dịch/chạy được với **Java 11**.

Đây là chủ đề **Cấu hình HTTP**. Bài không dùng thư viện HTTP cũ, không giả định Java HTTP Client là trình duyệt và không gán cho API những bảo đảm về việc bảo vệ credential mà tài liệu không cam kết.

## 1. Origin khác với phạm vi áp dụng cookie

### 1.1. Same-origin: scheme + host + port

Hai URI cùng origin khi cùng protocol scheme, hostname và cổng hiệu lực. Cổng mặc định là 80 cho HTTP, 443 cho HTTPS.

| URI A | URI B | Cùng origin? | Giải thích |
| --- | --- | --- | --- |
| `https://api.example.com/a` | `https://api.example.com/b` | Có | Cùng scheme, host, port 443 |
| `https://api.example.com/a` | `http://api.example.com/a` | Không | HTTP khác HTTPS |
| `https://api.example.com/a` | `https://api.example.com:8443/b` | Không | Khác cổng |
| `https://api.example.com/a` | `https://files.example.com/a` | Không | Khác host |
| `http://127.0.0.1:8001/a` | `http://127.0.0.1:8002/a` | Không | Hai cổng khác nhau |

Nếu request có credential gắn với API A, một chính sách bảo mật chặt chẽ thường **không tự gửi credential khi origin thay đổi**. Nếu thực sự cần gửi sang nhiều origin, phải có **allowlist cụ thể** theo credential/quyền, thay vì quy tắc rộng “cùng công ty” hoặc “host bắt đầu bằng chuỗi X”.

**Không kiểm tra host bằng `startsWith("api.example.com")`** trên URL nguyên văn. Một hostname giả như `api.example.com.evil.test` có thể vượt qua kiểm tra prefix ngây thơ. Hãy parse `URI`, so scheme/host/port và kiểm soát DNS/network egress nếu URL không tin cậy.

### 1.2. Cookie scope không dựa trên port như same-origin

Cookie HTTP có phạm vi gắn với host/domain và path, cùng những ràng buộc như `Secure`, thời gian hết hạn; **port không phải biên phân tách cookie**. Vì vậy một cookie được đặt tại `http://127.0.0.1:8001` có thể được gửi tới `http://127.0.0.1:8002` nếu có cùng host và phù hợp các thuộc tính.

Điều đó tạo ra khác biệt quan trọng:

- **Origin khác nhau** chưa đủ để kết luận cookie được tách riêng.
- Một `CookieManager` dùng chung có thể gửi cùng session cookie tới nhiều dịch vụ **cùng host, khác cổng**.
- `CookiePolicy.ACCEPT_ORIGINAL_SERVER` kiểm soát **chấp nhận cookie từ response**, **không** làm cookie chỉ tồn tại cho đúng TCP port đã đặt.
- Để cách ly các tenant/dịch vụ, hãy dùng **CookieStore riêng**, ranh giới host/domain phù hợp hoặc cơ chế xác thực không lưu cookie chung.

Ví dụ ở phần 5 sẽ cho kết quả `crossOriginBlocked=true` nhưng `other-cookie=true` trên hai cổng khác nhau. Đây **không phải mâu thuẫn**: hai phép kiểm tra sử dụng hai chính sách khác nhau.

## 2. Chính sách redirect của Java HttpClient

Tạo client:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Đây là đoạn minh họa, cần import `java.net.http.HttpClient`. Các enum được hỗ trợ từ Java 11:

| Chế độ | Ý nghĩa | Rủi ro và lựa chọn |
| --- | --- | --- |
| `Redirect.NEVER` | Không tự động theo redirect; **mặc định** khi không cấu hình | Phù hợp khi cần kiểm tra `Location`, chính sách header/cookie từng đích |
| `Redirect.NORMAL` | Theo redirect nhưng **không tự theo HTTPS → HTTP** | Ngăn downgrade, **không phải** same-origin policy |
| `Redirect.ALWAYS` | Cho phép redirect tự động kể cả downgrade | Không nên chọn mặc định cho request chứa token hoặc dữ liệu nhạy cảm |

**Lưu ý then chốt:** `NORMAL` không có nghĩa “chỉ follow trong cùng host” hoặc “chỉ follow trong cùng origin”. Nếu A và B đều HTTPS nhưng khác host, `NORMAL` **không phải** quy tắc chặn chuyển sang B theo origin. Cả `NORMAL` và `ALWAYS` đều không thay thế allowlist dành cho ứng dụng.

Trong redirect 3xx, method có thể thay đổi theo status. Ghi chú JDK cho biết `301` và `302` có thể khiến `POST` thành `GET`; các status `307` và `308` có ngữ nghĩa giữ method. Khi body là stream hoặc hành động có side effect, phải xác định **method/body có thể phát lại hay không**, không tự mặc định mọi redirect đều lặp nguyên request.

### Vì sao API có credential thường chọn `NEVER`?

Nếu URL do đối tác hoặc người dùng tác động có thể trả `Location: https://another.example.net/path`, tự động theo redirect có thể đưa request sang **một ranh giới bảo mật khác**. Với `NEVER`, ứng dụng nhận response `3xx` trước rồi thực hiện:

1. Kiểm tra status đúng loại redirect cần hỗ trợ.
2. Lấy và parse `Location`; dùng `previousUri.resolve(location)` cho URL tương đối.
3. Giới hạn scheme HTTP/HTTPS theo policy, ưu tiên HTTPS với dữ liệu nhạy cảm.
4. Kiểm tra host, port và allowlist (hoặc same-origin).
5. Tạo **HttpRequest mới**, chọn header/credential riêng cho destination.
6. Giới hạn số redirect hops, chống vòng lặp và có timeout tổng.
7. Kiểm tra body, method và tính idempotent trước khi phát lại POST/PUT.

**Không** phụ thuộc một hành vi không được đặc tả như “HttpClient chắc chắn sẽ luôn xóa Authorization khi redirect sang mọi host khác”. Cách an toàn có thể kiểm soát là **không bật auto redirect** cho request nhạy cảm và chỉ cấp credential khi destination đã được chấp thuận.

## 3. Header nào được mang theo khi đổi đích?

Các nhóm header có ý nghĩa khác nhau:

| Nhóm | Ví dụ | Chính sách đề xuất |
| --- | --- | --- |
| Nội dung thường | `Accept`, `Accept-Language` | Có thể dựng lại theo API đích, không cần copy nguyên |
| Credential | `Authorization`, `Cookie`, `X-API-Key` | Chỉ gửi tới origin/destination được cấp quyền |
| Thông tin tenant/nội bộ | `X-Tenant-ID`, request context, internal tracing ID | Cân nhắc như thông tin nhạy cảm; không gửi sang bên ngoài tùy tiện |
| Header body | `Content-Type`, checksum, content encoding | Phải khớp body và method thực tế của request mới |
| Header transport/framing | `Host`, `Content-Length`, `Transfer-Encoding` | Không sao chép bừa; để HttpClient/BodyPublisher quản lý theo giao thức |

Ví dụ hai request dùng **cùng HttpClient** nhưng khác credential:

```java
HttpRequest authorized = HttpRequest.newBuilder(apiUri)
        .header("Authorization", "Bearer demo-only")
        .header("Accept", "application/json")
        .GET()
        .build();

HttpRequest publicRead = HttpRequest.newBuilder(publicUri)
        .header("Accept", "application/json")
        .GET()
        .build();
```

Đây là đoạn minh họa với `URI apiUri` và `URI publicUri` đã được kiểm tra, import `HttpRequest`. Token `demo-only` là dữ liệu giả; production phải lấy secret từ nơi quản lý an toàn. Không tạo một `HttpRequest.Builder` có thể thay đổi dùng chung giữa các thread.

**Bỏ Authorization ở request B vẫn chưa đủ nếu HttpClient được gắn CookieManager chung**: client có thể tự gắn cookie phù hợp cho B dù ứng dụng không đặt header `Cookie`. Cần xem cả **header policy** và **cookie policy**.

### Cookie và Authorization không giống nhau

`Authorization` do code đặt trên request thường cần chính sách theo **origin/credential audience**. Cookie do `CookieManager` quản lý được lựa chọn theo phạm vi cookie, **không phải theo port của origin**. Do đó tránh một quy tắc chung “nếu khác origin thì tất cả header tự động an toàn” khi bạn vẫn dùng một CookieStore chung.

Ngoài ra, header `Cookie` do lập trình viên chủ động đặt là một vấn đề riêng. **Không có CookieManager** không có nghĩa request chắc chắn không chứa cookie do code tự thêm. Hãy kiểm soát cả hai con đường.

## 4. CookieManager, CookiePolicy và CookieStore

Java 11 có ba thành phần chính:

- `java.net.CookieManager`: `CookieHandler` cụ thể, điều phối nhận/gửi cookie giữa HTTP request và response.
- `java.net.CookiePolicy`: chính sách quyết định **có chấp nhận cookie được server trả về** hay không.
- `java.net.CookieStore`: nơi lưu cookie được nhận, phục vụ lựa chọn cookie phù hợp cho request tiếp theo.

Cấu hình:

```java
CookieManager manager = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(manager)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Đoạn này minh họa, cần import `CookieManager`, `CookiePolicy` và `HttpClient`. Truyền `null` làm CookieStore sẽ dùng store in-memory mặc định của CookieManager. Nếu **không** cấu hình `cookieHandler(...)`, `client.cookieHandler()` có thể là `Optional.empty()`; không được mặc định Java HTTP Client tự giữ session như browser.

### Các CookiePolicy chuẩn

| Policy | Ý nghĩa | Nhận xét |
| --- | --- | --- |
| `CookiePolicy.ACCEPT_NONE` | Không nhận cookie mới vào store | Thích hợp khi API stateless không cần cookie |
| `CookiePolicy.ACCEPT_ORIGINAL_SERVER` | Chỉ chấp nhận cookie do server gốc phù hợp gửi | Policy mặc định của CookieManager; không phải chia cookie theo port |
| `CookiePolicy.ACCEPT_ALL` | Chấp nhận cookie từ mọi server theo quy tắc này | Có thể giữ cookie không mong muốn; cân nhắc kỹ |

**Hai bước cần phân biệt:** `CookiePolicy.shouldAccept(URI, HttpCookie)` được dùng khi CookieManager **nhận** cookie, còn `CookieManager.get(URI, headers)` lựa chọn cookie **gửi** theo URI/thuộc tính/store. Chọn `ACCEPT_ORIGINAL_SERVER` không bảo đảm chỉ gửi cookie tới đúng một origin với cùng port.

### Thuộc tính cookie và cảnh báo thực tế

- **`Domain`:** giới hạn hoặc mở rộng phạm vi host theo quy tắc cookie. Đừng đặt Domain quá rộng khi các subdomain có mức tin cậy khác nhau.
- **`Path`:** giới hạn đường dẫn, nhưng **không phải cơ chế phân quyền** giữa hai ứng dụng độc lập trên cùng host.
- **`Secure`:** yêu cầu chỉ gửi cookie trên kết nối bảo mật thích hợp, thông thường HTTPS. Production cần HTTPS cho toàn bộ phiên nhạy cảm.
- **`HttpOnly`:** có ý nghĩa ngăn script client-side đọc cookie trong browser; **không** ngăn Cookie header được gửi trong HTTP request.
- **`Max-Age`/`Expires`:** quản lý vòng đời cookie; cần xử lý xóa phiên/đăng xuất.
- **`SameSite`:** là một thuộc tính quan trọng trong **trình duyệt hiện đại**. Không mặc định cho rằng `java.net.CookieManager` của Java 11 áp dụng đầy đủ ngữ nghĩa SameSite như Chrome/Firefox. Cần kiểm thử client và server thực tế.

Đừng dùng tiêu chí `HttpOnly=true` hay `SameSite=Lax` để kết luận “Java server-side client sẽ tuyệt đối không gửi cookie sang một đích khác”. Phải thiết kế đúng ranh giới lưu/gửi cookie ở ứng dụng.

### CookieManager dùng chung giữa nhiều người dùng

Một `HttpClient` có thể dùng nhiều request; đó là lợi thế reuse kết nối. Tuy nhiên, nếu một `CookieManager` lưu session cookie cho user A và B rồi cùng được dùng cho cả hai, có nguy cơ **lẫn session**.

Nên phân tách **CookieStore/HttpClient theo tenant, user session hoặc vùng trust** tùy kiến trúc. Nếu tạo hai HttpClient nhưng cả hai cùng dùng **một CookieManager instance**, việc tách client không giúp tách cookie. Nếu không cần cookie, đừng gắn store mặc định “cho tiện”.

Việc đặt `CookieHandler.setDefault(...)` toàn JVM không cần thiết để cấu hình một HttpClient cụ thể. Dùng `HttpClient.newBuilder().cookieHandler(manager)` để phạm vi rõ ràng, tránh ảnh hưởng HTTP stack khác.

## 5. Ví dụ độc lập: hai server cùng host, khác port

**Mục tiêu kiểm thử:** A trả HTTP 302, đồng thời đặt cookie. Redirect từ A sang B có **khác origin** vì khác port; một kiểm tra same-origin chặn việc tự gửi credential sang B. Tuy nhiên, cùng CookieManager vẫn có thể tự gửi cookie của A tới B vì **cookie không phân tách theo port**.

Hai HTTP server chạy trên `127.0.0.1` với cổng do hệ điều hành cấp, không dùng mạng Internet hoặc token thật. Server B chỉ kiểm tra **có hay không** header, không in giá trị bí mật.

**Tệp `MultiDestinationPolicyDemo.java` — Java 11+**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class MultiDestinationPolicyDemo {
    private static void reply(HttpExchange exchange, String message)
            throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static int effectivePort(URI uri) {
        if (uri.getPort() != -1) {
            return uri.getPort();
        }
        if ("https".equalsIgnoreCase(uri.getScheme())) {
            return 443;
        }
        if ("http".equalsIgnoreCase(uri.getScheme())) {
            return 80;
        }
        return -1;
    }

    private static boolean sameOrigin(URI left, URI right) {
        return left.getScheme() != null
                && right.getScheme() != null
                && left.getHost() != null
                && right.getHost() != null
                && left.getScheme().equalsIgnoreCase(right.getScheme())
                && left.getHost().toLowerCase(Locale.ROOT)
                        .equals(right.getHost().toLowerCase(Locale.ROOT))
                && effectivePort(left) == effectivePort(right);
    }

    private static HttpRequest get(URI uri) {
        return HttpRequest.newBuilder(uri).GET().build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer a = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        HttpServer b = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        try {
            String aBase = "http://127.0.0.1:" + a.getAddress().getPort();
            String bBase = "http://127.0.0.1:" + b.getAddress().getPort();

            a.createContext("/start", exchange -> {
                exchange.getResponseHeaders().set(
                        "Location", bBase + "/inspect");
                exchange.getResponseHeaders().add(
                        "Set-Cookie", "session=demo; Path=/; HttpOnly");
                exchange.sendResponseHeaders(302, -1);
                exchange.close();
            });
            a.createContext("/inspect", exchange ->
                    reply(exchange, "source-cookie="
                            + (exchange.getRequestHeaders()
                                    .getFirst("Cookie") != null)));
            b.createContext("/inspect", exchange -> {
                boolean gotCookie = exchange.getRequestHeaders()
                        .getFirst("Cookie") != null;
                boolean gotAuthorization = exchange.getRequestHeaders()
                        .getFirst("Authorization") != null;
                reply(exchange, "other-cookie=" + gotCookie
                        + ", other-authorization=" + gotAuthorization);
            });
            a.start();
            b.start();

            CookieManager cookies = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            HttpClient client = HttpClient.newBuilder()
                    .cookieHandler(cookies)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            URI source = URI.create(aBase + "/start");
            HttpRequest first = HttpRequest.newBuilder(source)
                    .header("Authorization", "Bearer demo-only")
                    .GET()
                    .build();
            HttpResponse<Void> initial = client.send(
                    first, HttpResponse.BodyHandlers.discarding());

            URI next = source.resolve(initial.headers()
                    .firstValue("Location").orElseThrow(
                            () -> new IllegalStateException("Missing Location")));
            System.out.println("status=" + initial.statusCode());
            System.out.println("crossOriginBlocked=" + !sameOrigin(source, next));

            // Hai request GET riêng, KHÔNG đi theo redirect.
            HttpResponse<String> fromA = client.send(
                    get(URI.create(aBase + "/inspect")),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            HttpResponse<String> fromB = client.send(
                    get(URI.create(bBase + "/inspect")),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println(fromA.body());
            System.out.println(fromB.body());
        } finally {
            a.stop(0);
            b.stop(0);
        }
    }
}
```

**Lệnh biên dịch và chạy:**

```bash
javac -encoding UTF-8 MultiDestinationPolicyDemo.java
java MultiDestinationPolicyDemo
```

Muốn xác minh không sử dụng API mới hơn Java 11:

```bash
javac --release 11 -encoding UTF-8 MultiDestinationPolicyDemo.java
java MultiDestinationPolicyDemo
```

**Stdout đã được kiểm tra bằng biên dịch và chạy thực tế:**

```text
status=302
crossOriginBlocked=true
source-cookie=true
other-cookie=true, other-authorization=false
```

`HttpServer` thuộc module JDK `jdk.httpserver`, có sẵn trong JDK thông thường. Mã chỉ phục vụ demo, **không phải hệ thống production xử lý dữ liệu nhạy cảm**.

### Phân tích chính xác kết quả

1. `initial` nhận status **302**, vì client dùng `Redirect.NEVER`. A trả `Location` tới B và `Set-Cookie`.
2. `sameOrigin(source, next)` trả `false` do **khác port**. Dòng `crossOriginBlocked=true` thể hiện chính sách ứng dụng **không tự gửi tiếp token theo Location**.
3. A đặt cookie có tên `session`, host `127.0.0.1` và `Path=/`. Request sau tới `/inspect` của A nhận `source-cookie=true`.
4. Chương trình **cố ý gửi một request khác** tới B, không có Authorization nhưng dùng cùng CookieManager. B báo `other-cookie=true` vì cookie cùng host và path phù hợp **không tách theo port**.
5. B báo `other-authorization=false` vì request kiểm tra B được **dựng mới mà không gắn Authorization**, không phải vì Java bảo đảm mọi redirect tự động sẽ xóa header đó. Demo **không** auto-follow redirect sang B.

**Bài học lớn nhất:** chính sách kiểm tra origin có thể chặn redirect của ứng dụng nhưng vẫn không tự chặn việc CookieManager gửi cookie sang một request khác ở cùng host/cổng khác. Trong production, không tạo request thử kiểu này với cookie thật; thay bằng test với cookie giả và cách ly store/host theo nhu cầu.

### Giới hạn của helper sameOrigin

Helper trong ví dụ đủ minh họa scheme/host/port. Với **đích không tin cậy**, cần kiểm tra thêm scheme HTTP/HTTPS hợp lệ, `URI.getUserInfo()`, host/port allowlist, DNS, địa chỉ IP nội bộ, proxy, redirect hop và mạng đầu ra. **Không lấy helper này làm tường lửa SSRF đầy đủ**. Nếu ứng dụng hoạt động qua proxy hoặc DNS thay đổi, policy hạ tầng và kiểm soát egress cũng cần được áp dụng.

## 6. Thiết kế chính sách redirect thủ công

Khi nhận `Location` từ server, không chỉ làm:

```java
URI next = previous.resolve(location);
HttpRequest request = HttpRequest.newBuilder(next).GET().build();
```

Đây là **đoạn minh họa**, giả sử có `URI previous` và `String location`. Nó chưa quyết định **next** có được phép truy cập hoặc nhận credential không.

Quy trình thực tế nên có:

1. **Status**: chỉ xử lý những loại redirect được API hỗ trợ; `304 Not Modified` không phải lệnh chuyển URI tới đích mới.
2. **Location**: parse bằng `URI`, resolve URI tương đối, từ chối URI không hợp lệ.
3. **Scheme/host/port**: kiểm tra theo allowlist. Với credential, thường yêu cầu HTTPS, tránh chuyển từ HTTPS xuống HTTP.
4. **Same-origin hoặc allowlist**: một request chuyển sang host mới cần được cấp quyền riêng. “Cùng domain gốc” không đương nhiên là cùng quyền.
5. **Header**: chọn whitelist header cho destination mới; **không sao chép token/cookie/API key** theo thói quen.
6. **Cookie**: chọn client và CookieStore thuộc đúng session/tenant, cân nhắc khả năng cookie tự động đính kèm.
7. **Method/body**: xác định chính sách 301/302/303/307/308; với body không replay được hoặc POST có tác dụng phụ phải tuân thủ hợp đồng nghiệp vụ.
8. **Giới hạn**: timeout, tối đa số hop, visited URI/loop detection, giới hạn response body, concurrency.
9. **Kết quả**: chỉ kết luận thành công khi nhận response cuối và xác minh logic nghiệp vụ.
10. **Theo dõi**: ghi metrics redirect count, rejected target, status; mask URL query/headers có secret.

Ví dụ kiểm tra trước khi tạo request:

```java
URI source = URI.create("https://api.example.com/start");
URI next = source.resolve("/next");

if (!sameOrigin(source, next)) {
    throw new SecurityException("Redirect origin not allowed");
}
HttpRequest nextRequest = HttpRequest.newBuilder(next)
        .header("Accept", "application/json")
        .GET()
        .build();
```

Đây là đoạn minh họa dùng helper `sameOrigin` đã định nghĩa ở ví dụ chính, import `URI` và `HttpRequest`. Nó **không** tự follow redirect; thiếu các kiểm tra SSRF, allowlist và body replay cần có trong sản phẩm.

### Đừng bỏ qua SSRF

Với backend nhận URL từ input hoặc redirect từ hệ thống bên ngoài, đích có thể là `localhost`, IP private, metadata service hoặc mạng nội bộ. Kẻ tấn công có thể tận dụng redirect hoặc DNS rebinding để khiến server của bạn truy cập nơi vốn không được phép.

Do đó cần **allowlist đích**, hạn chế scheme, chặn/kiểm soát địa chỉ IP nội bộ theo chính sách, xử lý DNS/proxy và kiểm soát egress. Không tắt xác minh TLS hostname/certificate chỉ để redirect thành công. Một phép so chuỗi `startsWith("https://api")` không phải biện pháp SSRF.

## 7. Một số chính sách mẫu theo loại dịch vụ

| Trường hợp | Redirect | Header nhạy cảm | Cookie |
| --- | --- | --- | --- |
| Gọi API nội bộ có bearer token | `NEVER` + allowlist hoặc chính sách được kiểm thử | Chỉ gửi token đến audience/origin được cấp quyền | Thường không cần cookie nếu stateless |
| Tải tệp qua CDN | Kiểm tra Location/allowlist CDN | Không tự mang bearer token API sang CDN | Không mang session cookie sang miền khác nếu không được phép |
| Một session web cần cookie | Theo hợp đồng ứng dụng, hạn chế downgrade | Không forward Authorization bừa bãi | CookieManager/store riêng cho session |
| Nhiều tenant cùng gọi một hostname | Redirect có policy theo tenant | Credential riêng tenant | Store riêng tenant/user |
| URL do người dùng cung cấp | Tránh auto-follow mù quáng | Không gắn secret nội bộ | Không dùng CookieManager có session nội bộ |
| Upload POST/PUT | Kiểm soát method/Location/redirect hops | Chỉ cấp credential được phép | Lưu ý idempotency và body replay |

Với client dùng chung, cần cân nhắc **cookie handler, proxy, authenticator, TLS config và quyền dữ liệu**, không chỉ lợi ích connection pooling. Hai client dùng CookieManager chung vẫn có thể chia sẻ cookie. Một `CookieManager` không có policy phân quyền theo user/tenant tự động.

### Chính sách cookie tối giản

Một ứng dụng stateless không cần cookie có thể không gắn CookieHandler, hoặc dùng:

```java
CookieManager cookies = new CookieManager(
        null, CookiePolicy.ACCEPT_NONE);
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookies)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Đây là đoạn minh họa không tự gửi request. Vẫn phải tránh **đặt thủ công header Cookie** nếu chính sách là không gửi session. Đừng dựa trên `CookiePolicy.ACCEPT_NONE` để xóa các header Cookie do code đã gắn.

## 8. Redirect với POST, upload và phương thức HTTP

Chính sách an toàn không dừng ở header. Nếu request là `POST` tạo đơn, upload file hoặc một lệnh cập nhật:

- HTTP `301`/`302` có thể làm `POST` thành `GET` tùy semantics/triển khai.
- `303` thường hướng client dùng `GET` để xem một tài nguyên kết quả theo giao thức.
- `307`/`308` yêu cầu chú ý việc giữ method và **phát lại body**.
- `BodyPublishers.ofInputStream(supplier)` có thể cần mở stream mới cho lần phát lại; nguồn chỉ đọc một lần có thể không replay được.
- Nếu server **đã xử lý** request nhưng redirect hoặc response bị mất, retry vô điều kiện có thể tạo side effect lặp. Thiết kế idempotency key/upload session/status check.

Đừng tự sao chép `Content-Length`, `Content-Type` hoặc Content-Encoding từ request cũ khi method/body đã đổi. Để HttpClient và BodyPublisher quản lý framing đúng với nội dung thực gửi.

## 9. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Dùng `Redirect.ALWAYS` với token và URL không tin cậy | Có thể chuyển sang host/protocol không được phép | `NEVER` và kiểm tra từng hop |
| Nghĩ `Redirect.NORMAL` chỉ follow same-origin | NORMAL chỉ chặn HTTPS→HTTP, không phải kiểm tra host | Same-origin/allowlist riêng |
| Copy toàn bộ headers sau 302 | Rò bearer token, Cookie, API key hoặc tenant ID | Dựng request mới theo chính sách destination |
| Giả định HTTP Client luôn tự bỏ Authorization khi redirect | Phụ thuộc trạng thái/API/triển khai; không phải policy của app | Tắt auto-follow khi cần kiểm soát secret |
| So URI bằng prefix chuỗi | Dễ nhầm hostname giả/trùng tiền tố | Parse URI và so scheme/host/port |
| Nghĩ cookie được tách theo port | Dịch vụ khác port trên cùng host có thể nhận cookie | Store/host riêng; test thực tế |
| Hiểu `ACCEPT_ORIGINAL_SERVER` là chỉ chấp nhận và gửi cookie trên cùng TCP port | Policy nhận cookie, không phải sandbox origin | Phân biệt accept và send scope |
| Gắn chung CookieManager cho nhiều tenant | Có thể lẫn session cookie | CookieStore riêng |
| Tưởng HttpOnly cấm Java gửi Cookie | HttpOnly là thuộc tính liên quan browser script | Hiểu cookie vẫn được gửi theo request |
| Mặc định Java CookieManager áp dụng SameSite như trình duyệt | Hành vi có thể khác browser | Kiểm thử chính sách cần thiết trên runtime |
| Dùng `ACCEPT_ALL` không có yêu cầu | Nhận nhiều cookie không cần thiết | ACCEPT_NONE/ORIGINAL_SERVER hoặc custom |
| Theo redirect đến private IP/localhost từ URL công cộng | Rủi ro SSRF | Allowlist + egress/DNS kiểm soát |
| Redirect POST không xét method/replay | Có thể đổi method hoặc tạo tác dụng phụ lặp | Kiểm tra status, idempotency, body publisher |
| Không giới hạn số hop | Loop hoặc chuỗi redirect dài | Max hops, timeout, visited set |
| Log nguyên Cookie/Authorization | Lộ credential | Mask và hạn chế log |
| Tự đặt `Host`/`Content-Length` không theo đích mới | HTTP framing sai | Cho HttpClient quản lý |
| Tách HttpClient nhưng dùng cùng CookieManager | Session state vẫn chia sẻ | Tách CookieStore/handler |

## 10. Bài tập tự kiểm tra

**Bài 1.** `https://api.example.com/a` và `https://api.example.com:8443/b` có cùng origin? **Không**, khác port.

**Bài 2.** Cookie từ `http://127.0.0.1:9001` có thể gửi sang `http://127.0.0.1:9002` không? **Có thể**, nếu host/path và các thuộc tính phù hợp. Cookie không phân tách theo port.

**Bài 3.** `Redirect.NORMAL` có tự ngăn redirect từ `https://api.example.com` sang `https://other.example.net` không? **Không**, NORMAL không tương đương same-origin.

**Bài 4.** Có thể mang `Authorization: Bearer xyz` sang `https://cdn.example.net` do `Location` trả về không? **Chỉ khi credential đó được cấp phép cho đích CDN**; mặc định không copy.

**Bài 5.** Hai tenant sử dụng cùng CookieManager nhưng hai HttpClient khác nhau. Cookie đã tách chưa? **Chưa**, vì store/handler vẫn được dùng chung.

**Bài 6.** `CookiePolicy.ACCEPT_NONE` có tự loại header `Cookie` được bạn thêm thủ công vào HttpRequest? **Không nên giả định vậy**; kiểm soát header thủ công riêng.

**Bài 7.** Đổi `Path=/` trong ví dụ thành `Path=/restricted`, sau đó gọi `/inspect`. Cookie có thể biến mất vì **path request không phù hợp**. Kiểm tra runtime thực tế.

**Bài 8.** Thử đổi demo từ `Redirect.NEVER` sang `Redirect.NORMAL`. Lưu ý client có thể tự theo 302 sang B, khiến chính sách `sameOrigin` trong code chạy **sau** khi client đã gửi request. Vì vậy không dùng kiểu này cho credential thật mà không có biện pháp kiểm soát trước chuyển hướng.

**Bài 9.** Header `Location: http://127.0.0.1:8080/admin` từ một trang Internet có nên được backend theo ngay? **Không**, phải xác minh quyền mạng, allowlist và SSRF policy.

**Bài 10.** Nêu ba thứ không log nguyên văn: bearer token, session cookie, API key; URI query chứa secret cũng cần mask.

### Checklist production

1. Ranh giới **origin** và **cookie domain/path** đã được phân biệt?
2. Header Authorization/API key được cấp theo **đúng destination**?
3. Redirect có allowlist scheme/host/port và giới hạn hop?
4. Không có tự động HTTPS→HTTP downgrade hoặc gửi credential đến đích sai?
5. CookieManager/Store được tách theo tenant/session/trust?
6. Có kiểm tra host cùng port khác nhau có thể chia sẻ cookie không?
7. Có tránh giả định SameSite/HttpOnly của Java server-side y hệt browser?
8. Có chống SSRF, DNS rebinding và kiểm soát egress cho URL không tin cậy?
9. Có kiểm soát method/body/idempotency với POST/PUT redirect?
10. Test đúng **JDK/HTTP client/proxy** và không ghi secret vào log?

## Tài liệu tham khảo chính thức

- [Oracle Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): cấu hình client, redirect mặc định và cookie handler.
- [Oracle Java SE 11 — HttpClient.Redirect](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html): `NEVER`, `NORMAL`, `ALWAYS`.
- [Oracle Java SE 25 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `followRedirects`, `cookieHandler` và các cấu hình hiện hành.
- [Oracle Java SE 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): URI, header, method, body và timeout.
- [Oracle Java SE 11 — CookieManager](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/CookieManager.html): `CookieHandler`, `CookieStore` và `CookiePolicy`.
- [Oracle Java SE 25 — CookieManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/CookieManager.html): quản lý cookie còn áp dụng trong Java hiện đại.
- [Oracle Java SE 25 — CookiePolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/CookiePolicy.html): các chính sách `ACCEPT_ALL`, `ACCEPT_NONE`, `ACCEPT_ORIGINAL_SERVER`.
- [Oracle Java SE 25 — HttpCookie](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/HttpCookie.html): các thuộc tính cookie.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): redirect và header Location.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html): cookie domain/path và phạm vi cookie không theo port.

**Kết luận:** `Redirect.NORMAL` **không phải** chính sách same-origin. `CookiePolicy.ACCEPT_ORIGINAL_SERVER` **không** tách cookie theo port. Khi một ứng dụng Java 11 đi qua nhiều HTTP destination, hãy **kiểm tra redirect trước khi gửi credential, dựng header theo đích và cách ly cookie store theo session/tenant**, đồng thời dùng HTTPS và bảo vệ chống SSRF cho các URL không tin cậy.