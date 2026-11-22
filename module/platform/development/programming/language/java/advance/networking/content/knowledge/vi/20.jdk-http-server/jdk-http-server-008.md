# Filter, Authenticator và tách xử lý dùng chung trong HTTP server của JDK

**`com.sun.net.httpserver.HttpServer`** trong module **`jdk.httpserver`** là HTTP server nhỏ có sẵn trong JDK. Thay vì viết lặp logic xác thực, ghi dấu request, thêm header, kiểm tra method và đo thời gian trong mọi endpoint, ta có thể tách thành **`HttpContext`**, **`Filter`**, **`Authenticator`**, **`HttpHandler`** và các helper/service dùng chung.

Bài Knowledge thuộc **Java Advance - networking → HTTP server của JDK**. Trọng tâm không chỉ là cú pháp API mà còn là **phân ranh trách nhiệm**, thứ tự xử lý và tính an toàn khi nhiều HTTP requests chạy đồng thời.

~~~text
                   HttpServer
                       |
           chọn HttpContext theo path
                       |
              user Filter chain
                /          \
       pre-processing     chặn sớm (4xx)
                |
          authentication
                |
          HttpHandler
                |
          response status/body
                |
         post-processing/logging
~~~

**Sơ đồ mô tả trách nhiệm, không phải cam kết rằng mọi user filter đều chạy sau Authenticator.** Trong provider đã kiểm thử, một pre-filter vẫn có thể chạy và thêm response header ngay cả khi authentication cuối cùng từ chối request. Vì vậy filter tiền xử lý không được tự giả định `HttpExchange.getPrincipal()` đã có authenticated principal.

Hai chương trình Java 17+ hoàn chỉnh trong bài được chạy với HTTP server trên `127.0.0.1`, port do hệ điều hành cấp. Không cần Internet, không dùng tài khoản hoặc password thật.

## 1. Phân chia trách nhiệm của các lớp

| Thành phần | Vai trò | Cần lưu ý |
| --- | --- | --- |
| `HttpServer` | Bind port, nhận requests, dispatch sang context, quản lý executor | Đơn giản, không phải framework/gateway đầy đủ |
| `HttpContext` | Ánh xạ root path với handler và cấu hình filter/authentication | Có danh sách filters riêng và attributes dùng chung |
| `HttpHandler` | Xử lý request theo nghiệp vụ, tạo response | Phải tự kiểm tra quyền với tài nguyên cụ thể |
| `HttpExchange` | Trạng thái, headers, streams của một request/response | Dùng `setAttribute/getAttribute` cho metadata theo request |
| `Filter` | Xử lý pre/post hoặc chặn request sớm | Gọi `chain.doFilter` đúng một lần khi muốn đi tiếp |
| `Filter.Chain` | Chuyển điều khiển sang filter tiếp theo hoặc handler | Không phải vòng lặp để gọi handler nhiều lần |
| `Authenticator` | Xác minh credentials, quyết định Success/Retry/Failure | Authentication khác authorization |
| `BasicAuthenticator` | Xử lý HTTP Basic, gọi `checkCredentials` do bạn viết | Base64 không phải mã hóa; chỉ dùng qua HTTPS ngoài loopback |
| `HttpPrincipal` | Danh tính đã được authenticator chấp nhận | Handler lấy bằng `exchange.getPrincipal()` |
| `Executor` | Chạy tasks xử lý HTTP requests | Đặt bằng `setExecutor` **trước** `start` |

Ví dụ request `GET /secure/report/42`: Filter có thể gắn trace ID, Authenticator kiểm chứng credentials, còn handler phải kiểm tra người dùng đó có quyền xem report 42 hay không. Có tài khoản hợp lệ **không đồng nghĩa** được phép xem mọi dữ liệu.

## 2. HttpContext định tuyến theo prefix, không phải regex

Cấu hình server (snippet, chưa có import/main đầy đủ):

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);

HttpContext api = server.createContext("/api/", exchange -> {
    // Handler kiểm tra path/method rồi phản hồi.
});

server.start();
~~~

`createContext("/api/", handler)` liên kết một path prefix với handler. Khi nhận request, server tìm **prefix dài nhất** phù hợp; việc so khớp là literal và phân biệt chữ hoa/thường. Không có `{id}` hay router parameters tự động.

~~~text
Contexts:
    /
    /api/
    /api/admin/

Request /api/users       -> /api/
Request /api/admin/list  -> /api/admin/
Request /other           -> /
Request /API/users       -> /  (khác chữ hoa)
~~~

**Cảnh báo:** Context `"/api"` không có dấu slash cuối có thể match `"/apix"`. Với route group, ưu tiên `"/api/"` và kiểm tra path cụ thể trong handler. Nếu context chỉ là `"/api/"`, handler sẽ nhận cả `/api/foo` và `/api/bar`; phải phân nhánh/validate.

`HttpServer.create(addr, backlog)` nhận một TCP backlog. Backlog là số connection chờ được accept ở OS, **không** phải request rate limit, không thay body-size limit hay bounded executor queue. Port `0` là cách chọn cổng tạm tiện cho tests.

## 3. Filter chain hoạt động ra sao?

Một custom Filter định nghĩa:

~~~java
@Override
public String description() {
    return "Measure request time";
}

@Override
public void doFilter(
        HttpExchange exchange, Filter.Chain chain)
        throws IOException {

    long started = System.nanoTime();
    try {
        chain.doFilter(exchange);
    } finally {
        long durationNanos = System.nanoTime() - started;
        // Ghi vào histogram/metrics thread-safe của ứng dụng.
    }
}
~~~

Đây là **phần thân của lớp Filter**, không phải chương trình độc lập. `Filter.doFilter` có thể kiểm tra request headers, gắn attributes, bọc streams, gửi response từ chối hoặc cho tiếp tục bằng `chain.doFilter(exchange)`.

Nếu gắn Filter A trước Filter B:

~~~text
A.before
    B.before
        HttpHandler.handle(exchange)
    B.after
A.after
~~~

**Pre đi xuôi, post đi ngược.** Một Filter được phép kết thúc chain sớm bằng cách **không gọi** `chain.doFilter`, nhưng khi đó phải tự gửi HTTP response phù hợp và đóng resource đúng.

Không gọi chain hai lần:

~~~java
chain.doFilter(exchange);
chain.doFilter(exchange); // PHẢN VÍ DỤ: có thể xử lý/gửi response hai lần.
~~~

Một `HttpExchange` có một response logic; gửi response headers lần thứ hai thường dẫn đến lỗi I/O hoặc exchange không còn hợp lệ.

## 4. Filter.beforeHandler và Filter.afterHandler từ Java 17

Hai factory methods tiện lợi:

~~~java
Filter trace = Filter.beforeHandler(
        "Add trace header",
        exchange -> exchange.getResponseHeaders()
                .set("X-Trace-Id", "study-247"));

Filter statusLog = Filter.afterHandler(
        "Log response code",
        exchange -> System.out.println(
                "HTTP status: " + exchange.getResponseCode()));
~~~

`beforeHandler` chạy Consumer **trước** filter tiếp theo/handler. `afterHandler` chạy Consumer **sau** downstream. Cả hai là các convenience factories có từ Java 17.

**Dùng beforeHandler để thêm header trước khi response commit.** Không dùng `afterHandler` để sửa `Content-Type`, CORS hoặc security headers vì handler có thể đã gửi response. `afterHandler` tốt hơn cho metrics, logging, quan sát status.

Với hai `afterHandler` liên tiếp, các Consumers chạy theo **thứ tự ngược lúc đăng ký**, vì chain lồng nhau. Nếu cần đo cả các trường hợp downstream ném `IOException`, custom Filter có `try/finally` thường rõ ràng hơn.

**Bắt lỗi đúng contract:** Theo Javadoc, nếu filter bắt `IOException` do downstream phát sinh, phải rethrow nó. Không nuốt IOException rồi tạo một HTTP 200 giả để che giấu lỗi.

## 5. Đăng ký filter ở đúng context và đúng thời điểm

~~~java
HttpContext context =
        server.createContext("/reports/", reportHandler);

context.getFilters().add(
        Filter.beforeHandler("Add marker", exchange ->
                exchange.getResponseHeaders()
                        .set("X-App", "reports")));

context.getFilters().add(new RequestMetricsFilter());
~~~

Đây là **snippet kiến trúc**: `reportHandler` và `RequestMetricsFilter` do ứng dụng định nghĩa. Danh sách `context.getFilters()` là **live list** thực sự dùng khi dispatch; thay đổi sẽ ảnh hưởng đến những requests tiếp theo. Với ứng dụng thực tế, nên cấu hình đầy đủ **trước `server.start()`**, tránh chỉnh danh sách khi các threads đang xử lý requests vì dễ tạo ordering/race khó kiểm thử.

**Không có global filter tự động** cho mọi HttpContext. Muốn áp middleware chung tới ba contexts thì phải gắn vào cả ba, hoặc dùng hàm bootstrap/factory để tạo các context với danh sách filter thống nhất.

Có thể đăng ký **cùng một Filter instance** cho nhiều contexts nếu nó stateless hoặc thread-safe. Nếu instance giữ counter hoặc mutable state, quyết định rõ có muốn dùng chung counter hay không; đừng vô tình trộn dữ liệu của các tenant.

## 6. Short-circuit: chặn request trong Filter

Ví dụ guard chỉ cho phép GET (snippet thuộc `doFilter`):

~~~java
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");

    byte[] body = "method-not-allowed"
            .getBytes(StandardCharsets.UTF_8);
    exchange.sendResponseHeaders(405, body.length);

    try (OutputStream out = exchange.getResponseBody()) {
        out.write(body);
    }

    return; // Không gọi chain.doFilter().
}

chain.doFilter(exchange);
~~~

Filter gửi `405 Method Not Allowed`, header `Allow: GET` rồi **dừng chain**. Handler và các filter bên trong không được gọi.

Nên dùng short-circuit cho validation chung: phương thức không hỗ trợ, header bắt buộc bị thiếu, giới hạn request hoặc throttling. Nhưng một filter kiểm tra HTTP method **không thể thay cho Authenticator hoặc phân quyền theo tài nguyên**.

Nếu từ chối request có body, application cũng phải quản lý request input stream và connection reuse. Đóng exchange khi chưa tiêu thụ body có thể khiến underlying connection không được reuse; kiểm soát byte limits, tránh đọc body vô hạn chỉ để trả lỗi.

## 7. Authenticator trả Success, Retry hoặc Failure

Trong `com.sun.net.httpserver.Authenticator`, method:

~~~java
public abstract Authenticator.Result authenticate(
        HttpExchange exchange);
~~~

phải trả một trong:

| Kết quả | Ý nghĩa | Hành vi chính |
| --- | --- | --- |
| `Authenticator.Success` | Danh tính/credentials hợp lệ | Tiếp tục xử lý handler, gắn HttpPrincipal |
| `Authenticator.Retry` | Client cần xác thực lại qua HTTP exchange khác | Trả status đã chỉ định, thường 401 và challenge |
| `Authenticator.Failure` | Authentication thất bại hoàn tất | Trả mã lỗi phù hợp, không chạy handler |

`Retry` **không phải server tự gọi lại handler**. Nó chỉ phát HTTP response để client có thể gửi request mới. Với Basic auth, client thường nhận `401` kèm `WWW-Authenticate: Basic realm="..."` rồi gửi lại credentials.

Gắn Authenticator cho một context:

~~~java
context.setAuthenticator(authenticator);
~~~

`setAuthenticator` thay thế authenticator trước đó; truyền `null` có thể xóa yêu cầu authentication của context, nên không làm việc này tùy tiện. Context khác không tự thừa kế Authenticator từ context hiện tại.

**Authentication và authorization khác nhau:** Authenticator kiểm chứng ai đang gửi request; handler phải kiểm tra danh tính đã được xác minh có được xem/sửa tài nguyên cụ thể không. Nếu thiếu authorization, có thể phát sinh IDOR/cross-tenant data leakage ngay cả khi Basic auth hoạt động hoàn hảo.

## 8. BasicAuthenticator và bảo mật HTTP Basic

Một ví dụ local:

~~~java
context.setAuthenticator(
        new BasicAuthenticator(
                "StudyRealm", StandardCharsets.UTF_8) {
            @Override
            public boolean checkCredentials(
                    String user, String password) {
                return "alice".equals(user)
                        && "demo-only".equals(password);
            }
        });
~~~

Đây là snippet dùng **credentials giả trên localhost**, không phù hợp production. `BasicAuthenticator` parse header HTTP Basic và gọi `checkCredentials(username,password)`. Constructor có tham số charset hỗ trợ UTF-8 từ Java 17; constructor không chỉ rõ charset có hành vi theo default charset trong Javadoc.

**Basic header chỉ chứa Base64 encoding, không mã hóa.** Trên đường truyền qua mạng phải dùng HTTPS/TLS, credential verification an toàn, password hashes/identity provider, chính sách chống brute-force, rate limit, secret rotation và logging được redact. Không hardcode plaintext password của user thực vào source.

Bảo vệ endpoints:
- Nếu request thiếu credential, BasicAuthenticator có thể trả 401 challenge.
- Nếu user/password sai, request bị từ chối.
- Nếu hợp lệ, handler lấy principal bằng `exchange.getPrincipal()`.
- Principal hợp lệ **không có nghĩa** được phép truy cập mọi object/tenant.

**Không dùng `X-User` hoặc IP người gửi như authenticated principal.** Các headers do client gửi có thể bị giả mạo; reverse proxy cũng cần trust boundary rõ ràng.

## 9. Thứ tự filters và authentication: điểm rất dễ nhầm

Trong provider đã được kiểm thử, response HTTP 401 vẫn mang header do `Filter.beforeHandler` thêm. Điều này cho thấy custom pre-filter có thể chạy **trước khi authentication kết thúc**.

Hãy giữ các bất biến an toàn:
1. User filter tiền xử lý được phép quan sát method/URI và tạo trace, nhưng không tự tin `getPrincipal()` đã khác null.
2. Không coi `X-User` hoặc `Authorization` chưa xác minh là danh tính hợp lệ.
3. Không tiết lộ thông tin nhạy cảm trong filter chạy ngay cả với requests chưa authenticated.
4. Không để handler xử lý business sensitive nếu chưa vượt qua yêu cầu xác thực của context.
5. Trong handler, kiểm tra **authorization theo object/tenant** dựa trên principal đã xác thực.
6. Khi đổi HTTP server provider/phiên bản JDK, **kiểm thử authentication/filter behavior**, không dựa vào thứ tự nội bộ chưa được API contract cam kết.

`HttpContext.setAuthenticator` bảo đảm authentication gắn vào context, nhưng nó không có nghĩa bạn được bỏ kiểm tra quyền ở handler hoặc dùng pre-filter như một authorization gate.

## 10. Ví dụ Java 17+ hoàn chỉnh: Filter + BasicAuthenticator + 405 guard

Chương trình **`FilterAuthOrderDemo.java`** tạo HTTP server loopback với context `/secure/`:
- `OrderFilter` ghi sự kiện trước/sau chain.
- `Filter.beforeHandler` gắn attribute và response header `X-Trace-Id`.
- Method guard trả 405 cho POST mà không gọi handler.
- `Filter.afterHandler` ghi response status khi downstream handler chạy.
- `BasicAuthenticator` chấp nhận duy nhất `alice:demo-only`.
- HttpClient gửi tuần tự bốn requests: thiếu auth, sai password, đúng password và đúng password nhưng POST.

Tạo file **`FilterAuthOrderDemo.java`**:

~~~java
import com.sun.net.httpserver.BasicAuthenticator;
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FilterAuthOrderDemo {
    static final List<String> events = new CopyOnWriteArrayList<>();

    static void send(HttpExchange ex, int status, String message)
            throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    static class OrderFilter extends Filter {
        @Override
        public String description() {
            return "Record filter nesting";
        }

        @Override
        public void doFilter(HttpExchange ex, Chain chain)
                throws IOException {
            events.add("outer-in");
            try {
                chain.doFilter(ex);
            } finally {
                events.add("outer-out");
            }
        }
    }

    static HttpRequest request(
            URI uri, String method, String basic) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3));

        if (basic != null) {
            String encoded = Base64.getEncoder().encodeToString(
                    basic.getBytes(StandardCharsets.UTF_8));
            builder.header("Authorization", "Basic " + encoded);
        }

        if ("GET".equals(method)) {
            builder.GET();
        } else {
            builder.method(method, HttpRequest.BodyPublishers.noBody());
        }
        return builder.build();
    }

    static String call(HttpClient client, HttpRequest req)
            throws Exception {
        HttpResponse<String> resp = client.send(
                req, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        return resp.statusCode() + "|" + resp.body()
                + "|trace=" + resp.headers()
                .firstValue("X-Trace-Id").orElse("none");
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        ExecutorService workers = Executors.newFixedThreadPool(3);
        server.setExecutor(workers);

        HttpContext context = server.createContext(
                "/secure/", ex -> {
                    events.add("handler");
                    String user = ex.getPrincipal() == null
                            ? "anonymous"
                            : ex.getPrincipal().getUsername();
                    send(ex, 200, user + "|" + ex.getAttribute("trace"));
                });

        context.getFilters().add(new OrderFilter());

        context.getFilters().add(Filter.beforeHandler(
                "Attach trace", ex -> {
                    events.add("trace-pre");
                    ex.setAttribute("trace", "lesson-247");
                    ex.getResponseHeaders().set(
                            "X-Trace-Id", "lesson-247");
                }));

        context.getFilters().add(new Filter() {
            @Override
            public String description() {
                return "Method guard";
            }

            @Override
            public void doFilter(
                    HttpExchange ex, Chain chain) throws IOException {
                events.add("guard");

                if (!"GET".equals(ex.getRequestMethod())) {
                    ex.getResponseHeaders().set("Allow", "GET");
                    send(ex, 405, "method-not-allowed");
                    return;
                }
                chain.doFilter(ex);
            }
        });

        context.getFilters().add(Filter.afterHandler(
                "Record response status",
                ex -> events.add("after:" + ex.getResponseCode())));

        context.setAuthenticator(new BasicAuthenticator(
                "StudyRealm", StandardCharsets.UTF_8) {
            @Override
            public boolean checkCredentials(
                    String user, String password) {
                return user.equals("alice")
                        && password.equals("demo-only");
            }
        });

        server.start();
        try {
            URI uri = URI.create(
                    "http://127.0.0.1:"
                    + server.getAddress().getPort()
                    + "/secure/hello");

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            System.out.println("No auth: " + call(
                    client, request(uri, "GET", null)));
            System.out.println("Wrong auth: " + call(
                    client, request(uri, "GET", "alice:incorrect")));

            events.clear();
            System.out.println("Valid auth: " + call(
                    client, request(uri, "GET", "alice:demo-only")));
            System.out.println("Valid events: "
                    + String.join(",", events));

            events.clear();
            System.out.println("Guard: " + call(
                    client, request(uri, "POST", "alice:demo-only")));
            System.out.println("Guard events: "
                    + String.join(",", events));
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FilterAuthOrderDemo.java
java FilterAuthOrderDemo
~~~

**Stdout kiểm thử với provider mặc định trong môi trường đã chạy (Java 17-compatible APIs):**

~~~text
No auth: 401||trace=lesson-247
Wrong auth: 401||trace=lesson-247
Valid auth: 200|alice|lesson-247|trace=lesson-247
Valid events: outer-in,trace-pre,guard,handler,after:200,outer-out
Guard: 405|method-not-allowed|trace=lesson-247
Guard events: outer-in,trace-pre,guard,outer-out
~~~

**Đọc kết quả:** Không auth và sai password đều 401, không vào handler. Pre-filter vẫn gắn `X-Trace-Id` trong provider thử nghiệm, nên output chứa trace dù không có authenticated principal. Với credentials hợp lệ, handler trả username và trace. Dãy sự kiện cho thấy outer filter bọc toàn bộ chain và afterHandler chạy khi inner handler kết thúc. POST bị method guard chặn 405 nên không có sự kiện handler/after:200.

**Không dùng code credentials này trên Internet.** Đây chỉ là fixture local để minh họa API, không có password hashing, lockout, CSRF controls, TLS hay policy production.

## 11. Tách xử lý dùng chung giữa nhiều endpoint

Một architecture có thể áp cùng các concerns lên nhiều contexts:

~~~text
        /alpha/hello --> AlphaHandler
       /alpha/other --> AlphaHandler
         /beta/hello --> BetaHandler
                   |
          +--------+--------+
          | common filters |
          | trace / metrics|
          +--------+--------+
                   |
          shared response helper
                   |
          endpoint-specific logic
~~~

Nên tách:
- **Filter dùng chung:** trace/correlation ID, metrics, kiểm tra method chung, response security headers trước commit, request limits.
- **Authenticator:** xác minh danh tính dựa trên credential mechanism của context.
- **Handler/service:** route chính xác, parse request body, xử lý data, authorization theo principal và resource, trả response.
- **Response support:** encode UTF-8, status, headers, responseLength, đóng body stream.
- **Bootstrap:** tạo contexts, gắn filters theo thứ tự, cấu hình Authenticator/Executor, start và stop.

Nếu handler alpha và beta dùng cùng một helper, điều đó không có nghĩa được phép dùng chung trạng thái `currentUser`. Những mutable fields trên Filter/Handler singleton có thể bị nhiều HTTP threads ghi/đọc đồng thời.

## 12. Per-request attribute và per-context attributes khác nhau

**`HttpExchange.setAttribute/getAttribute`** phù hợp với metadata của **một request**:

~~~java
Filter trace = Filter.beforeHandler(
        "Trace", ex -> ex.setAttribute("trace", "demo-247"));

// Handler nhận cùng HttpExchange:
Object requestTrace = exchange.getAttribute("trace");
~~~

Đây là snippet; trong production trace ID nên được tạo/validate theo policy, không dùng một chuỗi cố định.

**`HttpContext.getAttributes()`** trả một Map được **chia sẻ cho mọi exchange** của context:

~~~java
HttpContext reports = server.createContext(
        "/reports/", reportsHandler);
reports.getAttributes().put("service", "reports");
~~~

Đây là snippet, giả định `server/reportsHandler` đã có. Cấu hình bất biến theo context có thể nằm ở đây. **Không** ghi `currentUser`, bearer token, request body hay thông tin từng HTTP request vào Map chung.

Nếu một Filter instance dùng trên cả context alpha và beta:
- Nếu stateless: có thể chia sẻ.
- Nếu giữ counter thread-safe: counter có thể **cố ý đếm chung**.
- Nếu giữ context-local config/counter: cân nhắc tạo **instance riêng mỗi context**.
- Nếu giữ mutable request identity field: **không an toàn**, cần chuyển sang exchange attributes hoặc local variables.

## 13. Ví dụ Java 17+ hoàn chỉnh: cùng Filter trên hai contexts

Chương trình **`SharedFilterModulesDemo.java`** tạo:
- Context `/alpha/` với cấu hình service `"alpha"`.
- Context `/beta/` với cấu hình service `"beta"`.
- **Một** `CountingFilter` với `AtomicInteger` dùng chung.
- **Một** `Filter.beforeHandler` gắn `trace` lên mỗi exchange, cũng dùng chung.
- Handler dùng service config riêng và trả HTTP 404 nếu path cụ thể không khớp.
- Ba HTTP GET gửi tuần tự để output count được kiểm soát.

Tạo file **`SharedFilterModulesDemo.java`**:

~~~java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class SharedFilterModulesDemo {
    static final class CountingFilter extends Filter {
        final AtomicInteger seen = new AtomicInteger();

        @Override
        public String description() {
            return "Count across contexts";
        }

        @Override
        public void doFilter(
                HttpExchange ex, Chain chain) throws IOException {
            int count = seen.incrementAndGet();
            ex.getResponseHeaders().set(
                    "X-Count", Integer.toString(count));
            chain.doFilter(ex);
        }
    }

    static void send(
            HttpExchange ex, int status, String body)
            throws IOException {
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(status, data.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(data);
        }
    }

    static void handle(HttpExchange ex) throws IOException {
        String service = String.valueOf(
                ex.getHttpContext().getAttributes().get("service"));
        String path = ex.getRequestURI().getPath();

        if (!"GET".equals(ex.getRequestMethod())) {
            ex.getResponseHeaders().set("Allow", "GET");
            send(ex, 405, "method-not-allowed");
            return;
        }
        if (!path.equals("/" + service + "/hello")) {
            send(ex, 404, "not-found");
            return;
        }

        send(ex, 200, service + "|" + ex.getAttribute("trace"));
    }

    static HttpResponse<String> request(
            HttpClient client, URI root, String path)
            throws Exception {
        HttpRequest req = HttpRequest.newBuilder(root.resolve(path))
                .timeout(Duration.ofSeconds(3)).GET().build();
        return client.send(
                req, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        HttpContext alpha = server.createContext("/alpha/", ex -> {
            try {
                handle(ex);
            } catch (IOException error) {
                ex.close();
            }
        });
        HttpContext beta = server.createContext("/beta/", ex -> {
            try {
                handle(ex);
            } catch (IOException error) {
                ex.close();
            }
        });

        alpha.getAttributes().put("service", "alpha");
        beta.getAttributes().put("service", "beta");

        CountingFilter sharedCounter = new CountingFilter();
        Filter sharedTrace = Filter.beforeHandler(
                "Per-request trace", ex -> {
                    ex.setAttribute("trace", "demo-247");
                    ex.getResponseHeaders().set(
                            "X-Trace", "demo-247");
                });

        alpha.getFilters().addAll(
                List.of(sharedTrace, sharedCounter));
        beta.getFilters().addAll(
                List.of(sharedTrace, sharedCounter));

        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            HttpResponse<String> a =
                    request(client, root, "/alpha/hello");
            HttpResponse<String> b =
                    request(client, root, "/beta/hello");
            HttpResponse<String> missing =
                    request(client, root, "/alpha/missing");

            System.out.println("Alpha: " + a.statusCode()
                    + "|" + a.body() + "|count="
                    + a.headers()
                    .firstValue("X-Count").orElse("none"));
            System.out.println("Beta: " + b.statusCode()
                    + "|" + b.body() + "|count="
                    + b.headers()
                    .firstValue("X-Count").orElse("none"));
            System.out.println("Missing: "
                    + missing.statusCode() + "|" + missing.body()
                    + "|trace=" + missing.headers()
                    .firstValue("X-Trace").orElse("none"));
            System.out.println("Shared filter invocations: "
                    + sharedCounter.seen.get());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SharedFilterModulesDemo.java
java SharedFilterModulesDemo
~~~

**Stdout đã kiểm tra trên localhost với các requests tuần tự:**

~~~text
Alpha: 200|alpha|demo-247|count=1
Beta: 200|beta|demo-247|count=2
Missing: 404|not-found|trace=demo-247
Shared filter invocations: 3
~~~

**Giải thích:** Cùng filter instance chỉ tạo trace cho exchange hiện tại. Cấu hình service nằm trong hai context riêng. Counter atomic được thiết kế để tổng hợp requests của **cả hai contexts**, nên cả 404 cũng làm giá trị tăng. Nếu requests chạy đồng thời, counts vẫn an toàn nhưng thứ tự số đếm gắn với alpha hay beta không được bảo đảm. Muốn hai counter riêng, tạo hai CountingFilter instances.

## 14. Response helper và vòng đời HttpExchange

Một helper có thể dùng chung:

~~~java
static void sendText(
        HttpExchange ex, int status, String text)
        throws IOException {
    byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
    ex.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8");
    ex.sendResponseHeaders(status, bytes.length);
    try (OutputStream out = ex.getResponseBody()) {
        out.write(bytes);
    }
}
~~~

**Gọi `sendResponseHeaders` trước `getResponseBody()`**, và đóng OutputStream để kết thúc exchange. Độ dài fixed response phải là **số bytes sau encoding**, không phải `String.length()`.

Javadoc `HttpExchange.sendResponseHeaders(code, length)`:

| Giá trị length | Nghĩa |
| --- | --- |
| Lớn hơn 0 | Phải ghi đúng số bytes đã khai báo |
| Bằng 0 | Dùng **chunked transfer encoding**, có thể gửi lượng body tùy ý |
| Bằng -1 | **Không có response body** |

Đừng nhầm `responseLength=0` với body zero bytes. Với HTTP 204, dùng no-body semantics phù hợp, ví dụ `sendResponseHeaders(204, -1)`, không viết body.

Đóng response OutputStream cũng đóng request InputStream nếu chưa đóng, nhưng **nên tiêu thụ request body có giới hạn** để hỗ trợ connection reuse; nếu đóng giữa chừng, connection có thể không được tái sử dụng. Các ví dụ chỉ xử lý requests nhỏ từ client tự kiểm soát.

## 15. Filter.setStreams và body processing

Filter có thể bọc request/response streams bằng:

~~~java
exchange.setStreams(
        wrappedRequestInputStream,
        wrappedResponseOutputStream);
~~~

Theo Javadoc, streams mới phải **wrap original streams**; truyền `null` cho một hướng nếu không muốn thay. Dùng khi cần giới hạn byte đọc, đo response bytes hoặc xử lý transform có contract rõ.

~~~text
original request InputStream
     -> limiting/counting InputStream
     -> handler đọc từng chunk

handler ghi bytes
     -> counting OutputStream
     -> original response OutputStream
~~~

Đây là **sơ đồ**, không phải implementation runnable. Không đọc trước toàn bộ body trong Filter rồi mong Handler đọc lại từ stream đã bị tiêu thụ. Nếu chỉ muốn trace/metrics đơn giản, dùng Filter không bọc streams để giảm nguy cơ lỗi.

**Body limit phải dựa trên bytes thực sự đọc.** Header `Content-Length` có thể thiếu hoặc không đủ để tin tưởng, nhất là khi chunked transfer encoding. Server công khai cần limit per-request, concurrency, timeouts và admission control.

## 16. Concurrency và state an toàn

Khi gắn một executor với nhiều worker threads, cùng một Filter/Handler object có thể xử lý nhiều requests đồng thời.

**Phản ví dụ:**

~~~java
class BadFilter extends Filter {
    String lastUser; // Mutable shared field.

    public String description() { return "Unsafe"; }

    public void doFilter(
            HttpExchange ex, Chain chain) throws IOException {
        lastUser = ex.getRequestHeaders().getFirst("X-User");
        chain.doFilter(ex);
    }
}
~~~

Đây là mã minh họa sai. Nó vừa có **data race** giữa HTTP worker threads, vừa tin header do caller gửi thay vì principal đã authenticated.

An toàn hơn:
- Local variables và `HttpExchange.setAttribute/getAttribute` cho request-scoped metadata.
- Immutable configuration đặt trong final fields hoặc context attributes được set trước start.
- `AtomicInteger`, `LongAdder` hoặc metrics registry thread-safe cho counters.
- Không lưu `currentUser` hoặc bearer token của request vào static field, context map hoặc singleton filter.
- Không dựa vào ThreadLocal tự lan truyền qua executor/callbacks.
- Với business logic, lấy principal đúng và kiểm tra authorization từng object.

**Executor:** `server.setExecutor(executor)` phải gọi trước `start()`. `Executors.newFixedThreadPool(K)` giới hạn số worker threads nhưng queue mặc định có thể không giới hạn, nên production cần bounded queue, timeouts và request admission control. Các ví dụ localhost dùng small fixed pool chỉ để kiểm tra cơ chế.

## 17. Lỗi, HTTP status và giới hạn gửi response

Một Filter/Handler có thể trả 400, 401, 403, 404, 405, 413, 429 hoặc 500 tùy lỗi. Phân biệt:
- `401`: authentication challenge/credentials chưa hợp lệ.
- `403`: đã hiểu request nhưng không cho phép truy cập theo policy.
- `404`: không có route/resource (có thể do handler hoặc server).
- `405`: method không được hỗ trợ; nên đặt `Allow`.
- `500`: lỗi server; không đưa stack trace/secrets ra client.

Nếu exception xảy ra **trước khi gửi response headers**, error boundary có thể tạo 500 an toàn. Nếu headers đã được gửi, **không được gửi response thứ hai**; nên log và đóng exchange theo policy. `exchange.getResponseCode()` có thể là -1 trước khi status được set.

Nếu Filter bắt được `IOException` từ `chain.doFilter`, Javadoc yêu cầu rethrow. Với logging/metrics dùng `try/finally` để không làm mất cleanup. Không tự động retry một HTTP exchange trong cùng Filter bằng cách gọi chain nhiều lần.

## 18. Bảo mật và triển khai thực tế

Hai ví dụ dùng HTTP loopback để kiểm thử API, **không phải mẫu triển khai Internet**. Khi mở server:
- Dùng HTTPS qua `HttpsServer`/`HttpsConfigurator` với `SSLContext` và chứng chỉ hợp lệ, hoặc TLS reverse proxy đã được kiểm soát.
- Không dùng Basic credentials chỉ Base64 trên đường truyền không mã hóa.
- Passwords phải được hash phù hợp, có rate limiting/chống brute-force, audit, credential rotation.
- Không log `Authorization`, Cookie, session ID, mật khẩu hoặc dữ liệu nhạy cảm.
- Phân quyền theo user/resource/tenant trong Handler/Service, không chỉ authenticate.
- Kiểm tra URI normalization/path matching, tránh route prefix quá rộng.
- Đặt request body limits, bounded queues và timeouts để chống resource exhaustion.
- Chỉ tin proxy headers từ trusted proxy; header `X-Forwarded-For` của client không mặc nhiên đáng tin.
- CORS/CSRF và cookie/session policy cần được thiết kế riêng nếu phục vụ browser.
- Header bảo mật cần đặt **trước** commit response; không đợi afterHandler.
- Chống SSRF nếu handler truy cập URL/backend do client cung cấp.
- Test 401/403/404/405/429 cùng cả GET/POST và lỗi I/O.

JDK HttpServer là API nhỏ thuận tiện học tập, nhưng không tự cung cấp mọi chức năng của một framework API gateway/production server.

## 19. Checklist tách xử lý dùng chung

| Câu hỏi code review | Kết quả mong muốn |
| --- | --- |
| Context paths có rõ ràng và kết thúc bằng slash khi phù hợp? | Không match nhầm `/apiX` |
| Filters được gắn vào đúng contexts chưa? | Không bỏ sót endpoint |
| Thứ tự pre/post filters đã được kiểm tra? | Có tests lồng nhau |
| Filter short-circuit có gửi/đóng response đúng? | Không treo client |
| Authenticator được gắn qua `setAuthenticator`? | Không nhầm với `Filter` |
| Filter có giả định principal đã xác thực không? | Không |
| Handler có kiểm tra authorization theo resource? | Có |
| Request metadata đặt ở đâu? | Trong `HttpExchange`, không global field |
| Context config đặt ở đâu? | `HttpContext.getAttributes()` hoặc immutable dependency |
| Shared metrics fields có thread-safe? | Có |
| Response headers được set trước commit? | Có |
| Response fixed length có dùng byte length đúng? | Có |
| Error handling có tránh double response? | Có |
| Executor/queue có giới hạn? | Có khi public traffic |
| Body/credentials có được bảo vệ? | Size limits, TLS, không log secrets |
| Có test cả 401, 405, shared filters và path 404? | Có |

## 20. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Viết trace/metrics lặp ở mọi handler | Code lặp, thiếu nhất quán | Tách Filter |
| Đặt business authorization trong Filter không biết object | Bỏ sót IDOR | Kiểm tra tại service/handler |
| Gắn BasicAuthenticator vào filter list | Sai API | Dùng `context.setAuthenticator` |
| Tưởng pre-filter luôn có principal | Nhận định xác thực sai | Không dựa vào thứ tự internal auth |
| Quên `chain.doFilter` | Handler không chạy | Call chain đúng khi pass-through |
| Gọi chain hai lần | Double response | Một lần xử lý một exchange |
| Filter chặn sớm nhưng không trả response | Request treo | Gửi 4xx và đóng stream |
| Sửa headers trong afterHandler | Too late sau commit | Set ở beforeHandler/helper |
| Dùng `String.length()` làm fixed body length | Hỏng UTF-8 framing | Dùng `bytes.length` |
| Tưởng responseLength 0 = no-body | Nhầm chunked | Dùng -1 cho no-body |
| Không đóng response stream | Resource leak/connection không được reuse | Try-with-resources |
| Shared mutable currentUser trên filter | Data race/rò user | Exchange attribute |
| Lưu request metadata vào context attributes | Requests ghi đè nhau | Context chỉ giữ shared config |
| Dùng shared Atomic counter nhưng nghĩ là per-context | Metrics sai | Separate instances hoặc labels |
| Sửa filter list sau start | Races/order khó lường | Cấu hình trước start |
| Dùng HTTP Basic qua HTTP public | Credentials có thể bị đọc | Bắt buộc TLS |
| Tin `X-User` là authenticated identity | User spoof | Authenticator principal |
| Dùng `/api` làm route prefix không cân nhắc | Match cả `/apix` | Dùng `/api/` và kiểm tra path |
| Không giới hạn executor queue/body | DoS/OOM | Bounded resources |
| Cố gửi 500 sau response đã commit | Double write | Log + abort/close |
| Không test unauthorized method/path | Thiếu bảo vệ | Integration tests có status assertions |

## 21. Câu hỏi tự kiểm tra

**1.** `HttpContext` và `HttpHandler` khác nhau?  
**Đáp án:** Context giữ root path và cấu hình filter/auth, handler thực hiện xử lý request cụ thể.

**2.** Hai filter A/B theo thứ tự; pre/post đi theo thứ tự nào?  
**Đáp án:** A.pre → B.pre → handler → B.post → A.post.

**3.** Filter có luôn phải gọi `chain.doFilter`?  
**Đáp án:** Không; khi chặn sớm có thể trả status rồi không gọi chain.

**4.** `Filter.afterHandler` có nên thêm Content-Type không?  
**Đáp án:** Không nên, vì response có thể đã commit.

**5.** `BasicAuthenticator` có phải `Filter` không?  
**Đáp án:** Không. Gắn qua `HttpContext.setAuthenticator`.

**6.** `Authenticator.Success` cung cấp gì?  
**Đáp án:** HttpPrincipal đại diện authenticated user.

**7.** Có principal đã xác thực nghĩa là được xem mọi resource?  
**Đáp án:** Không; handler/service vẫn phải authorization từng object/tenant.

**8.** Tại sao Basic Base64 không đủ an toàn qua HTTP public?  
**Đáp án:** Base64 chỉ encode, dễ giải mã; cần HTTPS/TLS và credential policy.

**9.** `HttpExchange.setAttribute` dùng cho phạm vi nào?  
**Đáp án:** Cho một exchange/request.

**10.** `HttpContext.getAttributes` dùng cho phạm vi nào?  
**Đáp án:** Chung cho mọi requests trong context đó.

**11.** Cùng một CountingFilter instance trên hai contexts sẽ đếm thế nào?  
**Đáp án:** Dùng chung counter, cần atomic/thread-safe nếu xử lý đồng thời.

**12.** Context `/api` có thể match `/apix` không?  
**Đáp án:** Có, do prefix matching; nên dùng slash/path checks.

**13.** `sendResponseHeaders(status, 0)` nghĩa là không có body?  
**Đáp án:** Không; 0 là chunked; -1 là no-body.

**14.** Vì sao dùng `bytes.length` thay `text.length()`?  
**Đáp án:** Độ dài body HTTP là bytes, UTF-8 có thể khác số UTF-16 characters.

**15.** Filter trước auth có chắc nhìn thấy authenticated principal?  
**Đáp án:** Không. Không được dựa vào thứ tự implementation chưa cam kết.

**16.** Khi filter từ chối method bằng 405, handler có chạy không?  
**Đáp án:** Không nếu filter trả response và không gọi chain.

**17.** `HttpServer.setExecutor` gọi trước hay sau `start()`?  
**Đáp án:** Trước `start()`.

**18.** Khi HTTP handler đã gửi headers rồi gặp exception, có nên gửi 500 response mới?  
**Đáp án:** Không. Không được commit response thứ hai; log, cleanup/abort theo policy.

## 22. Tài liệu chính thức

- [Java SE 17 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): các lớp server HTTP của JDK.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): tạo server, executor, start/stop và prefix routing.
- [Java SE 17 — HttpContext](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): filter list, attributes và authenticator.
- [Java SE 17 — Filter](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html): Chain, short-circuit, beforeHandler/afterHandler.
- [Java SE 17 — Filter.Chain](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.Chain.html): xử lý filter kế tiếp.
- [Java SE 17 — Authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Authenticator.html): Success/Failure/Retry.
- [Java SE 17 — BasicAuthenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/BasicAuthenticator.html): Basic auth, realm, checkCredentials.
- [Java SE 17 — HttpPrincipal](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpPrincipal.html): authenticated principal.
- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response lifecycle và attributes/streams.
- [Java SE 17 — HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HTTPS server và SSL configuration.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client dùng trong hai phép thử loopback.
