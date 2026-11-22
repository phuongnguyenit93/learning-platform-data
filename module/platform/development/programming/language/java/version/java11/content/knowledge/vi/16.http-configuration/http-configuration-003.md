# CookieHandler, CookieManager và phạm vi phiên trong Java 11 HTTP Client

## Mục tiêu bài học

HTTP về cơ bản là giao thức không lưu trạng thái giữa các request. Nhiều ứng dụng vẫn cần duy trì đăng nhập, giỏ hàng, tùy chọn hoặc một phiên làm việc qua nhiều request. Server có thể gửi header **`Set-Cookie`**; phía client quyết định có nhận, lưu và gửi lại cookie qua header **`Cookie`** khi request tiếp theo phù hợp.

Trong Java 11, HTTP Client chuẩn thuộc **`java.net.http`** tích hợp cơ chế cookie bằng **`HttpClient.Builder.cookieHandler(CookieHandler)`**. Một lựa chọn phổ biến là **`java.net.CookieManager`**, phối hợp **`CookiePolicy`**, **`CookieStore`** và **`HttpCookie`**.

Sau bài này, bạn có thể:

1. Phân biệt vai trò của **`CookieHandler`**, **`CookieManager`**, **`CookiePolicy`**, **`CookieStore`**, **`HttpCookie`** và cấu hình `HttpClient`.
2. Duy trì cookie phiên qua nhiều request, nhưng không vô tình chia sẻ phiên giữa người dùng hoặc đối tượng nghiệp vụ khác nhau.
3. Hiểu giới hạn gửi cookie theo **host/domain, path, scheme Secure**, vòng đời **Max-Age/Expires** và ý nghĩa **HttpOnly**.
4. Phân biệt **cookie phiên** với **phiên server**, **vòng đời CookieManager** với **vòng đời HttpClient**, cũng như cookie store trong RAM với lưu trữ bền vững.
5. Biết vì sao **CookieHandler.setDefault(...)`** dành cho cơ chế handler hệ thống không thay thế cấu hình rõ ràng của Java 11 `HttpClient.newBuilder().cookieHandler(...)`.
6. Dùng cookie ở Java 11 một cách hiện đại, an toàn theo yêu cầu ứng dụng; không tự cho rằng Java `CookieManager` có đầy đủ chính sách giống trình duyệt web mới, đặc biệt với **SameSite**.
7. Chạy và mở rộng bài kiểm thử HTTP cục bộ chứng minh nhận cookie, trả cookie, phạm vi path, chia sẻ/cô lập store, Secure, Max-Age=0, ACCEPT_NONE và xóa phiên.

**Special Note về tính hiện hành:** các API trong bài vẫn được hỗ trợ ở các JDK hiện đại. Nội dung không dựa vào cách dùng HTTP Client incubator trước Java 11, không chọn công nghệ cũ làm phương án mặc định, cũng không coi các quy tắc RFC 2965 trong Javadoc Java là mô tả đầy đủ về cookie browser hiện đại.

## 1. Cookie đi qua HTTP như thế nào?

### 1.1. Chu trình đăng nhập tối giản

Ví dụ một server xử lý đăng nhập hợp lệ rồi tạo phiên có mã định danh ngẫu nhiên, khó đoán. Một request có thể dẫn tới response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: sid=opaque-session-id; Path=/account; Secure; HttpOnly
Content-Type: text/plain; charset=UTF-8

logged-in
~~~

Trong ví dụ, `sid` là tên cookie, còn `opaque-session-id` là một **giá trị minh họa**, không phải mã định danh phiên dùng trong sản phẩm thực. Những lần truy cập tiếp theo phù hợp với phạm vi cookie có thể đính kèm:

~~~http
GET /account/profile HTTP/1.1
Host: example.com
Cookie: sid=opaque-session-id
~~~

Server đối chiếu mã phiên với trạng thái server-side để xác thực request. Cookie **không tự tạo tính bảo mật** và Java client không xác minh người dùng chỉ bằng sự hiện diện của một tên cookie.

Sơ đồ luồng:

~~~text
Java HttpClient                              HTTP server
      |                                            |
      |---- GET /login --------------------------->|
      |<--- Set-Cookie: sid=...; Path=/account -----|
      |                                            |
      | CookieHandler.put(response headers)        |
      | CookiePolicy -> CookieStore.add(...)        |
      |                                            |
      | CookieHandler.get(request URI/headers)      |
      |---- GET /account/profile ----------------->|
      |     Cookie: sid=...                         |
      |<--- HTTP response --------------------------|
~~~

`CookieHandler.put(...)` nhận cookie từ response; `CookieHandler.get(...)` cung cấp header cookie thích hợp cho request. `CookieManager` đã hiện thực hai phần này, gọi `CookiePolicy` khi chấp nhận cookie và sử dụng `CookieStore` để lưu/truy xuất. Bạn **không cần** tự sao chép chuỗi `Set-Cookie` sang `Cookie` trên mọi request nếu đã cấu hình handler đúng.

### 1.2. Các thành phần có trách nhiệm khác nhau

| Thành phần | Java 11 API | Trách nhiệm |
| --- | --- | --- |
| HTTP Client | `java.net.http.HttpClient` | Gửi request, nhận response, dùng cookie handler nếu được cấu hình. |
| Cookie abstraction | `java.net.CookieHandler` | Interface trừu tượng cho callback `get(uri, requestHeaders)` và `put(uri, responseHeaders)`. |
| Cookie implementation | `java.net.CookieManager` | Kết hợp chính sách và kho cookie. |
| Acceptance policy | `java.net.CookiePolicy` | Quyết định cookie nhận từ server có được lưu hay không. |
| Storage | `java.net.CookieStore` | Lưu, truy xuất, loại cookie hết hạn và xóa cookie. |
| Cookie metadata | `java.net.HttpCookie` | Tên, giá trị, domain, path, max-age, secure, HttpOnly... |
| Server session | Do ứng dụng server quản lý | Xác thực và lưu trạng thái theo session ID, hết hạn, thu hồi quyền truy cập. |

**Đừng đồng nhất CookieManager với cơ chế phiên ở server.** CookieManager giữ cookie tại client; việc session ID còn quyền truy cập hay đã bị thu hồi nằm ở server. Ngay cả khi client còn cookie, server có thể trả 401/403 nếu phiên không còn hợp lệ.

## 2. Cấu hình CookieManager cho HttpClient trong Java 11

### 2.1. Cấu hình tường minh theo phạm vi sử dụng

~~~java
// Minh họa: đặt trong class/method có imports tương ứng.
CookieManager jar = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(jar)
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
~~~

- Tham số **`store = null`** yêu cầu tạo kho mặc định **trong bộ nhớ**.
- Chính sách **`CookiePolicy.ACCEPT_ORIGINAL_SERVER`** chỉ chấp nhận cookie từ server nguồn theo kiểm tra domain của triển khai Java.
- `cookieHandler(jar)` gắn handler cho **client được xây dựng**.
- Cookie sẽ được gửi lại trong những request tiếp theo nếu phù hợp với scope và thời hạn.
- Một `HttpClient` sau khi build là đối tượng cấu hình bất biến; có thể dùng lại qua nhiều request.

Có thể viết ngắn:

~~~java
CookieManager jar = new CookieManager();
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(jar)
        .build();
~~~

Theo Javadoc, `new CookieManager()` cũng dùng in-memory store và chính sách `ACCEPT_ORIGINAL_SERVER` mặc định. Với ứng dụng có nhiều người dùng, ưu tiên **tạo và quản lý rõ ràng mỗi CookieManager theo phạm vi danh tính được phép**, thay vì gắn một cookie jar toàn cục dùng chung.

### 2.2. Client mặc định không tự có cookie jar chỉ vì gọi newBuilder

~~~java
HttpClient plainClient = HttpClient.newBuilder().build();

boolean hasHandler = plainClient.cookieHandler().isPresent();
// Với builder không gọi cookieHandler(...): false.
~~~

Javadoc `HttpClient.cookieHandler()` trả `Optional<CookieHandler>`; nếu builder không cung cấp handler, Optional rỗng. Vì vậy **không nên giả định** response `Set-Cookie` sẽ được lưu và phát lại bởi `HttpClient.newHttpClient()` mà không có cấu hình cookie.

**Phân biệt với global handler:**

~~~java
// Không nên coi đây là cấu hình tự động cho mọi Java 11 HttpClient.
CookieHandler.setDefault(new CookieManager());
~~~

`CookieHandler.setDefault(...)` thiết lập handler cấp hệ thống được API URL stream (như `HttpURLConnection`) tham khảo theo hợp đồng của nó. Đối với Java 11 `java.net.http.HttpClient`, hãy **gắn trực tiếp** bằng builder. Không phụ thuộc vào sự thay đổi global state vì rất dễ làm test chạy song song hoặc session người dùng khác bị ảnh hưởng.

### 2.3. Hai client với cùng jar hoặc khác jar

~~~java
CookieManager aliceJar = new CookieManager();

HttpClient aliceApiClient = HttpClient.newBuilder()
        .cookieHandler(aliceJar).build();

HttpClient aliceUploadClient = HttpClient.newBuilder()
        .cookieHandler(aliceJar).build();

// Khác HttpClient nhưng cùng CookieManager: cùng kho cookie.
HttpClient bobApiClient = HttpClient.newBuilder()
        .cookieHandler(new CookieManager()).build();

// Bob có kho riêng: không dùng cookie của Alice.
~~~

**Phạm vi phiên do cách bạn quản lý jar quyết định**, không phải chỉ do số lượng đối tượng HttpClient. Hai client cùng `CookieManager` có thể chia sẻ cookie; hai client dùng jar riêng thì kho tách nhau. Nếu cùng một instance HTTP Client được dùng để gửi request thay mặt nhiều người dùng, cookie jar đi kèm cũng có nguy cơ bị chia sẻ. Đây là lỗi phân tách tài khoản nghiêm trọng nếu hệ thống gửi cookie người A trong request của người B.

Trong mô hình đa tenant, tạo cookie jar theo phiên/danh tính riêng và quản lý vòng đời, hoặc dùng kiến trúc xác thực không phụ thuộc cookie tự động nếu phù hợp hơn. Phân cách bằng tên đối tượng Java đơn thuần không tạo boundary: phải xem **mối quan hệ tham chiếu thực** đến CookieManager/CookieStore.

## 3. CookiePolicy: cookie nào được phép vào kho?

Java 11 có ba chính sách dựng sẵn:

| `CookiePolicy` | Quyết định | Khi nào cân nhắc |
| --- | --- | --- |
| `ACCEPT_ORIGINAL_SERVER` | Chấp nhận cookie từ server gốc theo kiểm tra policy. | Mặc định hợp lý cho ví dụ client dùng cookie. |
| `ACCEPT_NONE` | Không chấp nhận cookie nhận từ response. | Client không cần duy trì session cookie. |
| `ACCEPT_ALL` | Chấp nhận cookie không phân biệt hạn chế origin-policy của lựa chọn mặc định. | Không nên bật rộng rãi mà không đánh giá phạm vi tin cậy. |

~~~java
CookieManager noCookies = new CookieManager(
        null, CookiePolicy.ACCEPT_NONE);

HttpClient stateless = HttpClient.newBuilder()
        .cookieHandler(noCookies)
        .build();
~~~

Nếu server trả `Set-Cookie`, `ACCEPT_NONE` từ chối lưu cookie trong store. Nhưng điều đó **không phải bộ lọc mọi cách gửi cookie**: nếu application code tự chèn `Cookie` header theo cơ chế khác, hoặc dùng custom client/handler, vẫn cần kiểm soát những nguồn đó. `CookiePolicy` chủ yếu quyết định **nhận cookie nào**, trong khi `CookieManager.get`/`CookieStore` và thuộc tính cookie điều khiển **gửi lại**.

`CookieManager.setCookiePolicy(CookiePolicy)` tồn tại nếu cần đổi policy; trong ứng dụng chạy đồng thời, nên cấu hình đầy đủ **trước khi chia sẻ manager cho nhiều request** để tránh hành vi thay đổi giữa chừng.

**Không dùng `ACCEPT_ALL` để chữa mọi lỗi scope:** khi cookies từ domain không phù hợp bị nhận vào cùng store, bạn có thể tăng nguy cơ rò rỉ. Trước hết kiểm tra Set-Cookie, host, domain, path, scheme và chính sách server.

## 4. Phạm vi gửi cookie: Domain, Path, Secure, HttpOnly

### 4.1. Domain và host

Một cookie không ghi `Domain` thường gắn với **host đã gửi nó**. Cookie có `Domain` được xác định phạm vi theo quy tắc domain tương ứng; đặt domain rộng có thể khiến cookie tới các subdomain ngoài mong đợi. `CookieManager` và `HttpCookie` Java 11 có lịch sử triển khai theo các thông số cũ của HTTP cookie (Javadoc còn tham chiếu RFC 2965), vì thế không được kết luận rằng mọi giới hạn đều giống một trình duyệt hiện đại theo RFC 6265/bản cập nhật.

**Host khác nhau:** hai URI khác hostname không mặc nhiên chia sẻ cookie. Cần phân biệt host, domain attribute, scheme, port và path.

**Port:** cookie HTTP thường **không được cô lập chỉ bằng số port**. Hai dịch vụ khác cổng nhưng cùng host có thể thuộc cùng phạm vi cookie; không dựa vào `localhost:8080` so với `localhost:9090` làm ranh giới người dùng. Java `HttpCookie` còn có thuộc tính `Port` lịch sử cho các trường hợp chỉ định rõ, nhưng nó **không thay thế** cơ chế phân tách session ở ứng dụng.

### 4.2. Path hạn chế request được gửi cookie

Cookie:

~~~http
Set-Cookie: sid=alpha; Path=/private; HttpOnly
~~~

sẽ được xét cho những đường dẫn thuộc phạm vi `/private`, ví dụ:

~~~text
/private/check     -> phù hợp
/private/account   -> phù hợp
/public/check      -> không phù hợp
~~~

Ví dụ Java cục bộ bên dưới kiểm tra trực tiếp rằng request `/private/check` có cookie, còn `/public/check` không có.

**Path là quy tắc gửi cookie, không phải hàng rào cấp quyền.** Đừng dựa vào việc đổi đường dẫn để bảo vệ các chức năng nhạy cảm: server phải kiểm tra session, người dùng, role và quyền trên **mỗi request**.

### 4.3. Secure

Cookie có thuộc tính:

~~~http
Set-Cookie: tlsOnly=beta; Path=/; Secure; HttpOnly
~~~

chỉ nên gửi qua giao thức bảo mật tương ứng, thường là HTTPS. Trong ví dụ Java này, cookie `Secure` **không được gửi trên `http://127.0.0.1`**, kể cả nếu store đã nhận thông tin từ response HTTP.

Đối với ứng dụng production có session authentication, hãy truyền cookie qua HTTPS, cấu hình TLS đúng và không gửi session ID qua HTTP thuần. **Không suy luận cookie Secure mã hóa bản thân giá trị cookie trong bộ nhớ hoặc ở cookie store**: nó hạn chế bối cảnh gửi cookie; dữ liệu trong process vẫn phải được bảo vệ.

### 4.4. HttpOnly

`HttpCookie.isHttpOnly()` cho biết cookie có cờ `HttpOnly`. Trong trình duyệt, thuộc tính này nhằm ngăn JavaScript đọc cookie qua những API script như `document.cookie`; nó **không** ngăn Java code có quyền truy cập `CookieStore` gọi `cookie.getValue()`.

**Nhận thức quan trọng:** Java `HttpClient` không phải một browser với tài liệu HTML, top-level site, script sandbox và chính sách tương tác người dùng. `HttpOnly` không thể được hiểu là biện pháp phân quyền bên trong một process Java đa tenant. Không ghi trực tiếp session cookie vào log, analytics, exception message hoặc debug output.

### 4.5. SameSite và các quy tắc của browser hiện đại

Server hiện đại thường sử dụng:

~~~http
Set-Cookie: sid=...; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`SameSite` điều khiển những trường hợp cross-site trong **ngữ cảnh trình duyệt**, giúp giảm một số dạng CSRF. **Java 11 `HttpCookie` không cung cấp thuộc tính `getSameSite()` hay `setSameSite()` trong API công khai.** Không giả định `CookieManager` mô phỏng đầy đủ thuật toán SameSite, cookie prefixes, partitioned cookies hoặc third-party cookie policy mới như browser.

Đối với **Java server phát cookie phục vụ browser**, áp dụng các quy định hiện hành tại framework/giao thức HTTP và test trên browser thực. Đối với **Java backend HTTP client**, không dùng cờ SameSite được server phát làm cơ chế duy nhất bảo vệ việc gửi request cross-site: kiến trúc Java HTTP client phải tự quản lý quyền truy cập, nguồn URL và credential policy.

## 5. Phạm vi thời gian: cookie phiên không đồng nhất với phiên server

### 5.1. `HttpCookie.getMaxAge()`

Javadoc `HttpCookie` mô tả `maxAge` theo giây:

| Giá trị max-age | Ý nghĩa |
| --- | --- |
| **`-1`** (mặc định nếu không được đặt) | Cookie kiểu **session**, không được yêu cầu lưu bền vững; trong ngữ cảnh trình duyệt thường tồn tại tới khi session browser kết thúc. |
| **`0`** | Yêu cầu cookie bị loại bỏ ngay. Server có thể dùng `Set-Cookie` cùng tên/path và `Max-Age=0` để yêu cầu xóa. |
| **`> 0`** | Cookie có tuổi thọ tối đa tương ứng, tính bằng giây. |

Cookie:

~~~http
Set-Cookie: sid=alpha; Path=/private; HttpOnly
~~~

không có `Max-Age` sẽ cho `HttpCookie.getMaxAge() == -1` trong ví dụ Java 11. Tuy nhiên, vì `CookieManager` mặc định giữ cookie **trong RAM**, Java backend không có một sự kiện «đóng tab trình duyệt» để tự xóa cookie kiểu session. Cookie có thể tiếp tục ở cùng `CookieStore` chừng nào bạn chưa xóa/thu hồi, cookie chưa hết hạn theo quy tắc tương ứng hoặc process chưa kết thúc.

Đừng gọi `HttpClient.newBuilder().build()` tạo client mới rồi nghĩ session cũ được chấm dứt: nếu client mới dùng **chung `CookieManager`**, nó vẫn nhận cùng cookie. Ngược lại, nếu client khác dùng **kho riêng**, nó không tự nhận cookie của client cũ.

### 5.2. In-memory không đồng nghĩa không có thời hạn

`new CookieManager()` dùng kho cookie trong bộ nhớ theo mặc định; **không tự lưu cookie ra file hay database**. Một cookie có `Max-Age=3600` có thể hết hạn sau thời gian đó trong store hiện tại, nhưng việc có tuổi thọ 3600 giây **không làm kho trong RAM trở nên persistent qua JVM restart**. Nếu ứng dụng thực sự cần khôi phục cookie khi khởi động lại, cần một `CookieStore` tùy chỉnh có cơ chế lưu bền vững và xử lý expire, bảo vệ bí mật, đồng bộ, phiên bản định dạng.

Đối với session đăng nhập, lưu session ID ra disk thường tăng rủi ro mất tài khoản nếu không thiết kế bảo mật phù hợp. Hãy xác định yêu cầu nghiệp vụ rõ ràng trước khi chọn persistence.

### 5.3. Sign-out ở client và hủy phiên ở server

Có ít nhất hai việc khác nhau:

**Xóa cookie phía client:**

~~~java
jar.getCookieStore().removeAll();
~~~

Thao tác này xóa **mọi cookie trong jar**; phù hợp khi jar chỉ dành cho một phiên được phép xóa toàn bộ. Nếu jar dùng cho nhiều domain/ứng dụng, cách này có thể xóa quá rộng; nên dùng `remove(uri, cookie)` đúng đối tượng hoặc tổ chức jar riêng từ đầu.

**Vô hiệu hóa session ở server:** server thu hồi session ID/token, thay đổi trạng thái đăng nhập và có thể trả:

~~~http
Set-Cookie: sid=; Path=/private; Max-Age=0; HttpOnly
~~~

Các thuộc tính phạm vi như `Path`/`Domain` cần khớp cookie cần xóa. **Xóa chỉ tại client không chứng minh server đã thu hồi phiên**; nếu một bản sao session ID khác còn tồn tại ở nơi khác, server có thể vẫn chấp nhận nếu chưa invalidate. Trong ứng dụng thực, cần xử lý logout ở cả hai phía theo hợp đồng xác thực.

## 6. Ví dụ Java 11 độc lập: quản lý session cookie bằng HTTP server cục bộ

Để không phụ thuộc Internet, chương trình dùng server HTTP loopback `127.0.0.1` với port tự chọn. Server có:

- `/login`: trả `Set-Cookie: sid=alpha; Path=/private; HttpOnly`.
- `/private/check`: echo header `Cookie` nhận được để kiểm tra hành vi cookie gửi lại.
- `/public/check`: cùng hostname nhưng path không hợp lệ với cookie `/private`.
- `/secure`: trả cookie có `Secure` để kiểm không gửi trên HTTP.
- `/logout`: trả `Set-Cookie` cùng tên/path và `Max-Age=0` để xóa.

**Lưu ý:** server này là **fixture kiểm thử**, không phải mẫu đăng nhập thực. `sid=alpha` cố định, HTTP không mã hóa, echo cookie ra response và không hề xác thực user là những lựa chọn **chỉ được dùng trên loopback để quan sát dễ dàng**. Không đưa kiểu login/echo cookie này vào production.

Tạo file **CookieSessionDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
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
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CookieSessionDemo {
    private static void check(boolean valid, String detail) {
        if (!valid) throw new AssertionError(detail);
    }

    private static void reply(HttpExchange exchange, int status, String content)
            throws IOException {
        byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static void login(HttpExchange exchange) throws IOException {
        exchange.getResponseHeaders().add(
                "Set-Cookie", "sid=alpha; Path=/private; HttpOnly");
        reply(exchange, 200, "logged-in");
    }

    private static void destroy(HttpExchange exchange) throws IOException {
        exchange.getResponseHeaders().add(
                "Set-Cookie", "sid=expired; Path=/private; Max-Age=0; HttpOnly");
        reply(exchange, 200, "signed-out");
    }

    private static void secure(HttpExchange exchange) throws IOException {
        exchange.getResponseHeaders().add(
                "Set-Cookie", "tlsOnly=beta; Path=/; Secure; HttpOnly");
        reply(exchange, 200, "secure-cookie-set");
    }

    private static void echo(HttpExchange exchange) throws IOException {
        List<String> cookies = exchange.getRequestHeaders().get("Cookie");
        String header = cookies == null ? "" : String.join("; ", cookies);
        reply(exchange, 200, header);
    }

    private static HttpResponse<String> get(HttpClient client, URI root,
                                            String endpoint) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(root.resolve(endpoint))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
    }

    private static HttpClient client(CookieManager manager) {
        return HttpClient.newBuilder()
                .cookieHandler(manager)
                .connectTimeout(Duration.ofSeconds(3))
                .version(HttpClient.Version.HTTP_1_1)
                .build();
    }

    private static boolean contains(HttpResponse<String> result, String item) {
        return result.body().contains(item);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService threads = Executors.newFixedThreadPool(2);
        server.setExecutor(threads);
        server.createContext("/login", CookieSessionDemo::login);
        server.createContext("/logout", CookieSessionDemo::destroy);
        server.createContext("/secure", CookieSessionDemo::secure);
        server.createContext("/private/check", CookieSessionDemo::echo);
        server.createContext("/public/check", CookieSessionDemo::echo);
        server.start();

        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            CookieManager aliceJar = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            HttpClient alice = client(aliceJar);
            HttpClient anonymous = HttpClient.newBuilder().build();
            HttpClient bob = client(new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER));

            check(anonymous.cookieHandler().isEmpty(),
                    "new builder has no cookie handler by default");
            check(!contains(get(anonymous, root, "/private/check"), "sid="),
                    "anonymous must not send cookie");
            check(get(alice, root, "/login").statusCode() == 200,
                    "login response");
            check(contains(get(alice, root, "/private/check"), "sid=alpha"),
                    "same cookie manager should send session cookie");
            System.out.println("PASS configured CookieManager and login");

            check(!contains(get(alice, root, "/public/check"), "sid="),
                    "Path=/private cookie cannot go to /public");
            check(!contains(get(bob, root, "/private/check"), "sid="),
                    "separate CookieManager isolates users");
            check(!contains(get(anonymous, root, "/private/check"), "sid="),
                    "client without handler remains anonymous");
            System.out.println("PASS path and session isolation");

            List<HttpCookie> all = aliceJar.getCookieStore().getCookies();
            HttpCookie sid = all.stream()
                    .filter(c -> "sid".equals(c.getName()))
                    .findFirst()
                    .orElseThrow(() -> new AssertionError("sid not stored"));
            check(sid.getMaxAge() == -1, "missing Max-Age is session cookie");
            check(sid.isHttpOnly(), "HttpOnly attribute parsed");
            check("/private".equals(sid.getPath()), "Path attribute parsed");
            check(!sid.hasExpired(), "new session cookie not expired");
            System.out.println("PASS session cookie attributes");

            HttpClient shared = client(aliceJar);
            check(contains(get(shared, root, "/private/check"), "sid=alpha"),
                    "different client can share cookie manager explicitly");
            System.out.println("PASS explicit store sharing");

            check(get(alice, root, "/secure").statusCode() == 200,
                    "secure cookie response");
            check(!contains(get(alice, root, "/private/check"), "tlsOnly="),
                    "Secure cookie must not be sent over HTTP");
            System.out.println("PASS Secure excluded from HTTP");

            check(get(alice, root, "/logout").statusCode() == 200,
                    "logout response");
            check(!contains(get(alice, root, "/private/check"), "sid="),
                    "Max-Age=0 must remove session cookie");
            System.out.println("PASS Max-Age zero deletes cookie");

            CookieManager reject = new CookieManager(
                    null, CookiePolicy.ACCEPT_NONE);
            HttpClient denied = client(reject);
            check(get(denied, root, "/login").statusCode() == 200,
                    "login endpoint status for reject policy");
            check(reject.getCookieStore().getCookies().isEmpty(),
                    "ACCEPT_NONE must not store response cookies");
            check(!contains(get(denied, root, "/private/check"), "sid="),
                    "reject policy never sends session cookie");
            System.out.println("PASS ACCEPT_NONE policy");

            CookieManager clearJar = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            HttpClient clearClient = client(clearJar);
            get(clearClient, root, "/login");
            check(contains(get(clearClient, root, "/private/check"), "sid="),
                    "initial cookie before clear");
            clearJar.getCookieStore().removeAll();
            check(!contains(get(clearClient, root, "/private/check"), "sid="),
                    "clear store must remove session");
            System.out.println("PASS explicit session clearing");

            System.out.println("ALL COOKIE SESSION TESTS PASSED");
        } finally {
            server.stop(0);
            threads.shutdownNow();
        }
    }
}
~~~

### Biên dịch và chạy

Dùng JDK 11 (hoặc JDK mới có thể compile target Java 11). `jdk.httpserver` chỉ dùng để chạy server thử nghiệm trên loopback, không phải thư viện HTTP Client bên thứ ba:

~~~bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 CookieSessionDemo.java
java --add-modules jdk.httpserver -cp . CookieSessionDemo
~~~

Kết quả stdout chính xác khi các assertion đều đúng:

~~~text
PASS configured CookieManager and login
PASS path and session isolation
PASS session cookie attributes
PASS explicit store sharing
PASS Secure excluded from HTTP
PASS Max-Age zero deletes cookie
PASS ACCEPT_NONE policy
PASS explicit session clearing
ALL COOKIE SESSION TESTS PASSED
~~~

Chương trình cố tình dùng một server ở cổng động, cookie giá trị đơn giản, các request GET và `BodyHandlers.ofString(UTF_8)`. Không cần API mới hơn Java 11: `HttpClient.cookieHandler()` trả `Optional`, `CookieManager.getCookieStore()` truy cập store, `HttpCookie.getMaxAge/isHttpOnly/getPath` đọc thuộc tính; tất cả đều có trong JDK 11.

Mỗi case kiểm riêng:

| Case | Bằng chứng |
| --- | --- |
| CookieManager configured | Cookie `sid` được server phát và `HttpClient` gắn jar gửi lại ở request phù hợp. |
| Path scope | `/private/check` thấy `sid` nhưng `/public/check` không. |
| Isolation | Jar Bob riêng và client không có handler đều không có cookie Alice. |
| Session attributes | `getMaxAge() == -1`, `isHttpOnly() == true`, `getPath() == "/private"`. |
| Explicit sharing | Một client khác dùng **cùng `aliceJar`** nhận cùng cookie. |
| Secure | Cookie `Secure` không được phát lên HTTP loopback. |
| Max-Age=0 | Header xóa cùng tên/path làm `sid` biến mất ở request sau. |
| ACCEPT_NONE | Store không nhận cookie và request tiếp theo không gửi cookie. |
| Manual clearing | `CookieStore.removeAll()` xóa trạng thái phiên của kho được chỉ định. |

Ở ví dụ này, `anonymous.cookieHandler().isEmpty()` kiểm trực tiếp việc client không được gắn CookieHandler. Chỉ tạo `CookieManager` mà **quên truyền vào builder** sẽ không cho hiệu quả tương tự.

Nếu chạy trên JDK mới, biên dịch `--release 11` bảo đảm mã nguồn chỉ dùng API công khai của Java 11 và phần module được khai báo. Để có độ tin cậy triển khai Java 11, vẫn nên chạy thêm chính test này trên **runtime Java 11 thực tế** trong CI.

## 7. Kiểm thử phạm vi phiên trong sản phẩm

Bài test trên chỉ minh họa quan hệ một host và vài path. Một dịch vụ thực tế có thể có nhiều hostname, subdomain, proxy, redirect, tenant, JVM và môi trường khác nhau. Nên tổ chức các bài kiểm thử sau.

### 7.1. Ma trận test về phạm vi

| Tình huống | Kỳ vọng nên xác minh |
| --- | --- |
| Login A, request thứ hai bằng client A có chung jar | Cookie hợp lệ được gửi lại. |
| Login A, request bằng client B có jar riêng | Không thấy cookie A. |
| Tạo client C mới nhưng chủ động dùng jar A | Thấy cookie A nếu scope khớp. |
| Path `/private` so với `/public` | Cookie `Path=/private` không ra ngoài path được phép. |
| Cookie có `Secure`, request qua HTTP | Không gửi cookie `Secure` qua HTTP thường. |
| Cookie hết hạn hoặc `Max-Age=0` | Không gửi cookie đã hết hạn/xóa. |
| `ACCEPT_NONE` | Từ chối cookie mới của response. |
| Đổi hostname | Cookie chỉ được gửi nếu quy tắc host/domain phù hợp. |
| Cùng hostname khác port | Không mặc định port là boundary; test theo quy tắc thực tế của client/server. |
| Redirect sang host khác | Không được phát tán cookie sang host ngoài scope; test cả redirect policy. |
| Tái sử dụng client sau khi jar bị clear | Không dùng lại cookie đã xóa. |
| Runtime/server restart | Không giả định store in-memory còn tồn tại hoặc server vẫn chấp nhận session ID cũ. |

**Lưu ý bảo mật:** không chạy bài test session bằng cách sử dụng cookie đăng nhập thật rồi ghi ra file kết quả. Dùng tài khoản test, session ID giả, endpoint nội bộ/localhost và xóa dữ liệu sau chạy.

### 7.2. Cần test bằng HTTPS ở lớp tích hợp

Demo dùng HTTP loopback để chứng minh rằng cookie có `Secure` **không được gửi** khi không có TLS. Nó **không** chứng minh rằng một hệ thống production đã thiết lập TLS đúng, không bị downgrade, xử lý certificate chain an toàn hoặc có đầy đủ chính sách cookie của browser.

Các hệ thống thực tế cần integration test qua HTTPS với certificate test hợp lệ, domain phù hợp, redirect policy, proxy và credentials. Không tắt xác minh TLS chỉ để làm cookie test qua được.

### 7.3. Cách nhìn vào CookieStore khi debug

~~~java
CookieStore store = jar.getCookieStore();
List<HttpCookie> cookies = store.getCookies();

for (HttpCookie cookie : cookies) {
    System.out.println(cookie.getName()
            + " path=" + cookie.getPath()
            + " secure=" + cookie.getSecure()
            + " httpOnly=" + cookie.isHttpOnly());
}
~~~

Đây là đoạn **minh họa** chỉ nên dùng trên dữ liệu test; nó in **metadata** chứ không in `cookie.getValue()`. Trong sản phẩm không log token/cookie nhạy cảm ngay cả ở mức debug, vì log thường được lưu lâu và nhiều người/hệ thống có thể đọc được.

`CookieStore.getCookies()` trả danh sách cookie chưa hết hạn; khi cần xem cookie cho một URI cụ thể, có thể dùng `store.get(uri)`. Tuy nhiên `CookieManager.get(uri, headers)` còn áp dụng các quy tắc như path/secure khi tạo header, do đó **danh sách trong store không đồng nghĩa mọi cookie được gửi đến mọi URL**.

## 8. Những lỗi và hiểu lầm thường gặp

1. **Cho rằng Java 11 `HttpClient` mặc định lưu cookie.** Cần cấu hình rõ `.cookieHandler(...)` nếu muốn cookie management.
2. **Gọi `CookieHandler.setDefault` rồi mặc định mọi HttpClient đã build sẽ dùng handler mới.** Sử dụng builder tường minh, tránh phụ thuộc trạng thái global.
3. **Dùng một cookie jar chung cho tất cả người dùng backend.** Session cookie A có thể xuất hiện ở request B; phân tách jar theo identity và quản lý lifecycle.
4. **Nghĩ session cookie hết hạn khi đóng một HttpClient instance.** Cookie nằm ở `CookieStore`; cùng store vẫn có thể được client khác dùng.
5. **Nghĩ `getMaxAge() == -1` nghĩa là cookie phải xóa ngay.** Đây là cookie phiên, không phải `Max-Age=0`.
6. **Nghĩ `Max-Age=3600` khiến mặc định cookie được ghi ra disk.** In-memory store vẫn không có persistence qua JVM restart.
7. **Coi `Path` là phân quyền server.** Path chỉ giới hạn gửi cookie, server phải kiểm quyền riêng.
8. **Coi hostname + port là session boundary.** Cookie bình thường không được cô lập chỉ bằng cổng; tránh chia sẻ host có cookie nhạy cảm giữa môi trường không tin cậy.
9. **Coi `HttpOnly` bảo vệ cookie khỏi Java backend code có quyền truy cập store.** Nó dành cho ngữ cảnh scripting/browser; Java code vẫn có thể đọc giá trị từ `HttpCookie`.
10. **Coi `Secure` là bằng chứng session ID tự được mã hóa trong RAM hoặc log.** `Secure` hạn chế giao thức gửi; vẫn cần TLS, bảo vệ secret và hạn chế logging.
11. **Giả định `CookieManager` áp dụng đầy đủ SameSite và các chính sách browser đời mới.** Java 11 `HttpCookie` không có getter/setter SameSite trong public API; không dùng nó để mô phỏng browser security model.
12. **Bật `ACCEPT_ALL` để chữa lỗi domain/path.** Làm tăng phạm vi chấp nhận cookie; kiểm Set-Cookie, policy và host trước.
13. **Chỉ xóa cookie client rồi coi logout an toàn tuyệt đối.** Server phải vô hiệu hóa session/token theo chính sách; cookie đã lộ có thể vẫn được sử dụng nếu server chấp nhận.
14. **Tự đặt header `Cookie` trên mọi request bằng String nối tay.** Dễ gửi nhầm hostname/path, bỏ qua hết hạn và làm lộ secret; dùng handler/store được cấu hình và test.
15. **Log `Set-Cookie` hoặc `Cookie` toàn bộ.** Có thể làm lộ định danh phiên; chỉ log metadata ít nhạy cảm.
16. **Không kiểm HTTP status sau login.** Server có thể trả 401/403/500, cookie không có hoặc vô hiệu; xác thực trạng thái nghiệp vụ trước khi coi đã đăng nhập.
17. **Quên kiểm redirect.** Khi client follow redirect giữa host/protocol, cần chắc chắn cookie chỉ được gửi theo đúng scope và policy đã chọn.
18. **Tự viết CookieStore persistent nhưng không có chính sách bảo mật.** Cần mã hóa phù hợp, hạn chế truy cập, xử lý expire, đồng bộ thread, chống ghi lỗi và tránh dữ liệu session tồn tại ngoài thời hạn.
19. **Cho rằng SameSite thay thế CSRF protection cho Java backend.** SameSite thuộc bối cảnh trình duyệt; API backend phải xác thực/ủy quyền và kiểm nguồn request theo mô hình riêng.

## 9. Câu hỏi tự đánh giá

**1.** `CookieManager` có phải là HTTP client không?

**Đáp án:** Không. Nó là một **`CookieHandler` cụ thể** quản lý policy + store. `java.net.http.HttpClient` mới là đối tượng gửi request; đưa manager vào `HttpClient.Builder.cookieHandler(...)`.

**2.** Hai `HttpClient` khác nhau có thể cùng dùng một cookie phiên không?

**Đáp án:** Có, nếu được cấu hình dùng **chung `CookieManager`/CookieStore** và URL phù hợp scope. Hai client có jar khác nhau không tự chia sẻ cookie.

**3.** Gọi `CookieHandler.setDefault(new CookieManager())` có phải cách nên dùng để cấu hình cookie cho một HttpClient Java 11 không?

**Đáp án:** Không nên dựa vào nó. Hãy dùng `HttpClient.newBuilder().cookieHandler(manager)` để xác định trực tiếp handler của client đó.

**4.** Cookie `Path=/private` có đi kèm request `/public/check` không?

**Đáp án:** Không theo kiểm thử của `CookieManager` Java 11; nó chỉ gửi trong phạm vi path phù hợp. Dù vậy, path không phải cơ chế phân quyền.

**5.** Cookie có `Secure` được gửi qua HTTP thường không?

**Đáp án:** Không; ví dụ kiểm chứng Java CookieManager loại cookie đó khỏi request `http://127.0.0.1`. Trong sản phẩm dùng HTTPS đúng.

**6.** `HttpOnly` có khiến `jar.getCookieStore().getCookies()` không đọc được cookie không?

**Đáp án:** Không. HttpOnly là hạn chế đối với scripting trong browser, không phải hệ thống phân quyền Java trong cùng process.

**7.** `HttpCookie.getMaxAge() == -1` có nghĩa gì? Có tự xóa ngay không?

**Đáp án:** Cookie phiên, không được thiết kế lưu bền vững; **không tự xóa ngay**. Phân biệt với `Max-Age=0`.

**8.** Nếu server trả `Max-Age=3600`, cookie sẽ tồn tại sau khi JVM restart chứ?

**Đáp án:** Không có bảo đảm khi dùng `CookieManager` mặc định, vì store là in-memory. Muốn persistence phải thiết kế riêng; điều này còn có rủi ro bảo mật.

**9.** Nếu ứng dụng cần xóa toàn bộ cookie của một phiên riêng biệt, phương thức nào dùng được?

**Đáp án:** `jar.getCookieStore().removeAll()` xóa toàn bộ cookie **trong jar đó**. Chỉ dùng khi jar dành cho phạm vi được phép xóa, và kết hợp server-side invalidation khi logout.

**10.** `CookiePolicy.ACCEPT_NONE` có nghĩa là request không bao giờ có header `Cookie` từ bất kỳ nguồn nào không?

**Đáp án:** Không. Nó từ chối việc **lưu cookie do response đưa tới** bằng manager. Không nên suy rộng sang header do code khác tự thêm; cần kiểm soát toàn đường gửi request.

**11.** Server cần bảo vệ endpoint theo role. Có thể chỉ dựa vào Path hoặc HttpOnly cookie không?

**Đáp án:** Không. Server phải xác thực phiên và kiểm quyền mỗi request. Domain/Path/Secure/HttpOnly là các thuộc tính truyền/lưu cookie, không thay thế authorization.

**12.** Vì sao không nên giả định Java `CookieManager` giống Chrome/Safari về SameSite?

**Đáp án:** Java 11 `HttpCookie` không có API SameSite chuyên biệt; trình duyệt có ngữ cảnh site, script, navigation, third-party và các chính sách riêng. Java backend HTTP client không đại diện cho toàn bộ ngữ cảnh đó.

## 10. Checklist áp dụng vào dự án

- [ ] Hiểu chính xác luồng `Set-Cookie` → `CookieHandler.put` → `CookieStore` → `CookieHandler.get` → `Cookie`.
- [ ] Cấu hình `HttpClient.Builder.cookieHandler(manager)` rõ ràng, không dựa vào global state.
- [ ] Chọn `CookiePolicy.ACCEPT_ORIGINAL_SERVER` hoặc chính sách phù hợp và tránh `ACCEPT_ALL` vô lý.
- [ ] Phân tách CookieManager giữa các phiên/danh tính không được phép chia sẻ cookie.
- [ ] Đánh giá host/domain/path/port, `Secure`, `HttpOnly`, `Max-Age` và redirect bằng test thực.
- [ ] Phân biệt session cookie, in-memory CookieStore, client lifetime và server session expiration.
- [ ] Xóa cookie đúng phạm vi khi logout, đồng thời thu hồi phiên ở server.
- [ ] Không log cookie values/session IDs và sử dụng HTTPS cho session thật.
- [ ] Không xem Java CookieManager là browser SameSite/CSRF engine.
- [ ] Chạy thành công `CookieSessionDemo.java` bằng `javac --release 11 --add-modules jdk.httpserver`.
- [ ] Có integration test HTTPS và isolation theo user/tenant trước khi triển khai môi trường nhiều người dùng.

## Tài liệu chính thức và tham khảo bảo mật

1. [Java SE 11 — `HttpClient.Builder.cookieHandler(CookieHandler)`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
2. [Java SE 11 — `HttpClient.cookieHandler()` và cấu hình client](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
3. [Java SE 11 — `CookieHandler`: `get`/`put` và system-wide default](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/CookieHandler.html)
4. [Java SE 11 — `CookieManager`: CookiePolicy + CookieStore](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/CookieManager.html)
5. [Java SE 11 — `CookiePolicy`: ACCEPT_ALL, ACCEPT_NONE, ACCEPT_ORIGINAL_SERVER](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/CookiePolicy.html)
6. [Java SE 11 — `CookieStore`: get/add/remove/removeAll](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/CookieStore.html)
7. [Java SE 11 — `HttpCookie`: Max-Age, Domain, Path, Secure, HttpOnly](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/HttpCookie.html)
8. [Java SE 26 — `CookieManager`: đối chiếu API tiếp tục được hỗ trợ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieManager.html)
9. [MDN HTTP Cookies — domain, path, SameSite, Secure và HttpOnly trong trình duyệt hiện đại](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
