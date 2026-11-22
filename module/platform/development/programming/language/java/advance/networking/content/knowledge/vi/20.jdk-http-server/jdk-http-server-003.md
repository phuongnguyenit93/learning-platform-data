# Quy tắc khớp tiền tố đường dẫn và phân biệt chữ hoa/chữ thường — HttpServer (Java 17+)

**`HttpServer` trong Java 17 tìm `HttpContext` có đường dẫn là tiền tố literal khớp dài nhất của URI path.** Phép so khớp **phân biệt chữ hoa/chữ thường** và **không tự thực hiện biến đổi sang/từ dạng percent-encoded** khi lựa chọn context. Hệ quả: `"/api"` có thể khớp cả `"/apiX"`, còn `"/api/admin/"` không khớp `"/api/Admin/"`. Đây là quy tắc định tuyến của API `com.sun.net.httpserver`, **không phải** router REST có path variables, method constraints hay authorization tự động.

Sai một ký tự, một dấu `/` hoặc một bước canonicalization có thể khiến request rơi vào context khác, đặc biệt nguy hiểm khi context cha là public còn context con yêu cầu xác thực. Bài thuộc nhóm **HTTP server của JDK** của **Java Advance - networking**, hướng dẫn cơ chế longest-prefix matching, boundary path, case sensitivity, raw/decoded URI, các cách guard an toàn và hai chương trình Java 17+ kiểm thử bằng HTTP loopback thực.

## 1. API liên quan và phạm vi chính xác

Module `jdk.httpserver` xuất bản các lớp `HttpServer`, `HttpsServer`, `HttpContext`, `HttpHandler`, `HttpExchange`, `Filter` và `Authenticator`. Bạn đăng ký một context với:

```java
// Snippet minh họa: server và handler đã được tạo.
HttpContext ctx = server.createContext("/api/", handler);
```

`HttpServer` tiếp nhận request, chọn **context path**, rồi gọi `HttpHandler.handle(HttpExchange)`. `HttpExchange.getHttpContext()` trả về context thực sự được chọn; `getRequestURI()` trả URI request. Một context có thể gắn filters và authenticator của riêng nó. `HttpsServer` bổ sung TLS nhưng không làm thay đổi việc cần thiết kế routing/app authorization.

Tách biệt **ba khái niệm**:

1. **Context selection** do JDK thực hiện: tìm literal path prefix dài nhất.
2. **Route resolution** do ứng dụng hoặc framework thực hiện: kiểm tra method, path segments, path parameters, query/header constraints.
3. **Authorization** do security/business layer thực hiện: principal được phép làm gì với resource cụ thể.

Context match đúng chỉ chứng minh đã gọi một handler, **không** chứng minh người dùng được quyền đọc, sửa hoặc xóa tài nguyên.

## 2. Longest matching prefix: quy tắc chọn chính

Ví dụ đăng ký contexts:

```text
"/"             -> ROOT
"/apps/"        -> APPS
"/apps/foo/"    -> FOO
```

Bảng lựa chọn theo API Java 17:

| URI path | Context được chọn | Vì sao |
| --- | --- | --- |
| `/apps/foo/bar` | `/apps/foo/` | Tiền tố khớp dài nhất |
| `/apps/app1` | `/apps/` | `/apps/foo/` không khớp |
| `/apps/Foo/bar` | `/apps/` | Chữ `F` khác `f` |
| `/Apps/foo/bar` | `/` | Không khớp lowercase `/apps/` |
| `/other` | `/` | Root prefix catch-all |
| `/apps` | `/` | `/apps/` có slash cuối, không khớp `/apps` |

**Thứ tự gọi `createContext()` không tạo priority kiểu first-match.** Nếu hai contexts đều khớp, prefix dài hơn được chọn. Không dùng thứ tự đăng ký làm cơ chế override hoặc phân quyền. Hai contexts có cùng path không được đăng ký trùng nhau trên cùng server.

Nếu **không có** root context `"/"`, request không khớp context nào có thể được server trả HTTP 404; ví dụ thực ở phần 12 xác nhận hành vi trên JDK.

## 3. Literal prefix không phải path-segment prefix

Một chuỗi `a` là tiền tố của chuỗi `ab` cho dù hai từ có ý nghĩa khác nhau. Với URL path, điều này dẫn đến prefix collision:

| Context | Request path | Kết quả trên Java 17 |
| --- | --- | --- |
| `/foo` | `/foo` | Khớp |
| `/foo` | `/foo/bar` | Khớp |
| `/foo` | `/foobar` | **Khớp** |
| `/v1` | `/v123` | **Khớp** |
| `/admin` | `/administrator` | **Khớp** |
| `/users` | `/users-backup` | **Khớp** |
| `/users/` | `/users-backup` | Không khớp |
| `/users/` | `/users/42` | Khớp |

Muốn xác định root `/users` và descendants thực sự của nó, một ứng dụng có thể dùng:

```java
// Snippet: path đã được kiểm tra theo canonical policy.
boolean inside = "/users".equals(path)
        || path.startsWith("/users/");
```

Cách này tốt hơn `path.startsWith("/users")` về **ranh giới phân đoạn**, nhưng **vẫn không tự giải quyết percent encoding, slash không chuẩn, dot segments hoặc authorization**. Context selection là bước ban đầu; handler cần guard bổ sung.

## 4. Dấu slash cuối: một ký tự thay đổi route

Với hai contexts:

```java
// Snippet: hai handler đã có, server chưa start.
server.createContext("/api", apiRootHandler);
server.createContext("/api/", apiChildrenHandler);
```

- `/api` vào `/api`.
- `/api/` vào `/api/` vì prefix dài hơn.
- `/api/items` vào `/api/`.
- `/apiX` vẫn vào `/api` **nếu handler không từ chối**.

Đăng ký **chỉ** `"/api/"` không tự bắt `"/api"`. Bạn cần quyết định API có chấp nhận cả hai, trả 404 cho bare path hay redirect theo semantics rõ. Với POST/PUT có side effect, redirect phải bảo toàn method/body và xét idempotency; không tự follow tùy tiện.

Java 17 Javadoc khuyên context paths nói chung **nên** kết thúc bằng `/`, bởi `"/foo"` sẽ khớp cả `"/foobar"`. Nhưng thêm slash **không phải cơ chế phân quyền**: `/api/private/../public` về mặt prefix vẫn trông nằm dưới `/api/` nếu input chưa được xử lý ở tầng khác.

## 5. Case sensitivity: admin khác Admin

Ví dụ:

```text
Context:
   /api/
   /api/admin/

Request                        Context chọn
/api/admin/status              /api/admin/
/api/Admin/status              /api/
/API/admin/status              không khớp (nếu không có /)
```

**Nguy cơ bảo mật:** nếu `/api/admin/` có filter xác thực, nhưng `/api/` là generic handler có thể tự lowercase path, request `/api/Admin/status` có thể lọt vào nhánh xử lý không được bảo vệ đúng. Đừng giả định “trông giống tên admin” nghĩa đã chạy qua filter của admin context.

Để phòng tránh, dùng canonical route rules thống nhất và kiểm tra authorization **theo resource/operation**, không dựa hoàn toàn vào việc JDK chọn context. Với route sai casing, có thể trả 404 rõ ràng thay vì tự sửa thành chữ thường.

Không lowercase toàn bộ URI path theo thói quen. Object keys, file names, URL resources, Unicode identifiers và storage lookups có thể **phân biệt chữ hoa**, trong khi một số proxies có behavior khác nhau. Việc chuẩn hóa path phải là **hợp đồng nhất quán của ứng dụng**.

## 6. Root fallback và 404 không giống nhau

`createContext("/", handler)` trở thành **fallback rất rộng** vì hầu hết HTTP request paths bắt đầu bằng `/`. Nếu bạn thêm root context, request `/unknown` hoặc `/API/foo` có thể vào root handler, thay vì được core server trả 404.

```java
// Snippet: root fallback cần chính sách rõ.
server.createContext("/", fallback);
server.createContext("/api/", api);
server.createContext("/api/admin/", admin);
```

Một SPA frontend có thể muốn root fallback trả HTML index cho trang UI, nhưng **không nên trả HTML 200 cho mọi API path không tồn tại**. Không để root handler định tuyến tới dữ liệu private bằng chuỗi lowercased/decoded nếu không có authorization đúng.

Một bộ log hữu ích nên phân biệt 404 do **không có context**, 404 do **handler từ chối path shape**, 404 do **resource không tồn tại**, và 403 do **không đủ quyền**. Cùng là HTTP status nhưng khác nguyên nhân điều tra.

## 7. URI path, query và HTTP method là các lớp riêng

Request:

```text
GET /api/item?sort=asc&page=2 HTTP/1.1
       ^^^^^^^^^
       URI path
                ^^^^^^^^^^^^^^^
                   URI query
```

`HttpServer` chọn context từ **URI path**, không từ query string. `/api/item?sort=asc` và `/api/item?sort=desc` khớp cùng prefix. `GET /api/item` và `POST /api/item` có thể được gửi đến **cùng handler**, vì `createContext` không phải method-aware router.

Phải tự kiểm tra `exchange.getRequestMethod()`, `exchange.getRequestURI().getRawQuery()`/`getQuery()` theo contract, cùng header/content-type và status 405 khi method không hỗ trợ.

Cũng đừng nhầm tên header (HTTP header field names là case-insensitive) với URI path: **path có case-sensitive semantics trong `HttpServer` Java 17**. `Host` hoặc `X-Forwarded-Host` không phải một phần thuật toán context-prefix selection; nếu app phân tenant qua host, phải thiết kế trusted-proxy/virtual-host validation riêng.

## 8. Đăng ký context: thứ tự không phải điều kiện đúng/sai

Cả hai cách sau đều phải cho kết quả longest-prefix giống nhau:

```java
// Thứ tự A
server.createContext("/api/admin/", admin);
server.createContext("/api/", api);
```

```java
// Thứ tự B trên một HttpServer khác
server.createContext("/api/", api);
server.createContext("/api/admin/", admin);
```

Request `/api/admin/users` vẫn vào context `/api/admin/`. Một path trùng chính xác không thể đăng ký hai lần trên cùng server như một cách overwrite: API có thể ném `IllegalArgumentException`. Nếu cần thay route hoặc deployment version, quản lý lifecycle và in-flight exchanges rõ ràng; `removeContext` không hồi tố hủy exchanges đang xử lý.

Khi cần biết server đã chọn context nào, đọc `exchange.getHttpContext().getPath()` thay vì đoán từ request path hoặc thứ tự đăng ký. Đó là công cụ QA quan trọng trong demo 1.

## 9. Raw path và decoded path có thể khác nhau

`HttpExchange.getRequestURI()` trả `java.net.URI`, trong đó:

- `URI.getRawPath()` giữ percent-encoded representation.
- `URI.getPath()` trả đường dẫn đã decode escape sequences theo API.

Ví dụ:

```text
Request-target: /docs/%61dmin
getRawPath():   /docs/%61dmin
getPath():      /docs/admin
```

Dữ liệu trong hai chuỗi không giống nhau. Một hệ thống có thể dùng raw form để kiểm tra canonical spelling, rồi parse resource ID sau một bước decode đã được xác định rõ. **Không decode hai lần**; chuỗi dạng `%252e` có thể thay đổi ý nghĩa qua nhiều lớp decode, dẫn tới sai khác với WAF/proxy.

**Tài liệu `HttpServer` Java 17 xác định literal path matching không tự conversion encoded forms.** Nhưng business routing và authz vẫn phải có policy riêng cho encoded paths, chứ không chỉ tin rằng request đã đi đúng context sẽ không có encoded alias.

## 10. Percent-encoded slash, dot segments và path traversal

Các đầu vào phải có chính sách rõ:

| Path form | Câu hỏi bảo mật |
| --- | --- |
| `/docs/admin` | Có phải canonical business resource? |
| `/docs/%61dmin` | Encoded alias có được phép, hay từ chối? |
| `/docs/%2Fprivate` | Sau decode dấu `/` có tạo segment mới? |
| `/docs/%2e%2e/secret` | Encoded `..` có dẫn đến traversal trong tầng sau? |
| `/docs/../admin` | Proxy hoặc URI normalization có thay path? |
| `/docs//item` | Có gộp nhiều slash hay giữ nguyên? |
| `/docs/%252e%252e` | Double encoding có gây decode hai lần? |
| `/Docs/item` | Casing khác canonical route? |
| `/docs/ITEM` | Resource ID có phân biệt hoa/thường? |

**Không có một thao tác lowercase/normalize/URL-decode tự động an toàn cho mọi ứng dụng.** Nếu API chỉ dùng ASCII slugs, việc từ chối phần trăm/Unicode/multiple segments có thể là policy dễ kiểm chứng. Nhưng **không nên cấm percent encoding toàn cục** trong API cần tên người dùng quốc tế hoặc URL hợp lệ có Unicode; khi đó cần quy ước canonicalization/validation nhất quán từ proxy đến backend.

Khi biến URI path thành đường dẫn file thật, còn phải dùng filesystem containment checks, canonical path, symlink policy và authorization theo file. `String.startsWith` trên raw URL path **không phải** biện pháp đủ để ngăn truy cập file ngoài thư mục gốc.

## 11. Segment-boundary guard với policy cụ thể

Nếu context là `"/docs"`, handler có thể nhận `/docs-public`. Kiểm tra tối thiểu:

```java
// Snippet bên trong handler, uri lấy từ getRequestURI().
String rawPath = uri.getRawPath();
boolean isDocs = "/docs".equals(rawPath)
        || rawPath.startsWith("/docs/");
if (!isDocs) {
    // 404/403 theo policy, nhớ đóng exchange.
}
```

Điều kiện này loại prefix collision nhưng vẫn cho phép nested paths, encoded aliases và dot segments. Với bài toán “chỉ chấp nhận root hoặc đúng **một slug ASCII lowercase**”, dùng:

```java
boolean accepted = "/docs".equals(rawPath)
        || rawPath.matches("/docs/[a-z0-9-]+");
```

Regex này **là yêu cầu minh họa của ứng dụng, không phải quy tắc Java**. Nó cố tình từ chối `/docs/a/b` và `/docs/%61dmin`. Nếu app cần Unicode/nested paths, thay bằng parser và normalization có thiết kế đúng; **không** bỏ authorization vì một regex đã match.

## 12. Java 17 runnable demo 1: longest prefix và case-sensitive thực tế

Tệp **`PathPrefixRoutingDemo.java`** chứa chương trình độc lập, chỉ dùng JDK. Server HTTP bind IPv4 loopback `127.0.0.1` và port tự cấp. Nó đăng ký 5 contexts:

```text
/api           -> BASE
/api/          -> SECTION
/api/admin/    -> ADMIN
/Api/          -> CAPITAL
/v1            -> VERSION
```

Mỗi handler ghi `LABEL@selected-context-path` bằng `exchange.getHttpContext().getPath()`. Client gửi **10 requests HTTP thật**, không phải chỉ test `String.startsWith` trong memory.

```java
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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class PathPrefixRoutingDemo {
    private static void respond(HttpExchange exchange, String label)
            throws IOException {
        try (exchange) {
            String body = label + "@" + exchange.getHttpContext().getPath();
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    private static void test(HttpClient client, String base, String path)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(base + path))
                .timeout(Duration.ofSeconds(5)).GET().build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        String result = response.statusCode() == 404
                ? "NO_CONTEXT" : response.body();
        System.out.println(path + " => "
                + response.statusCode() + "/" + result);
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(3);
        server.createContext("/api",
                exchange -> respond(exchange, "BASE"));
        server.createContext("/api/",
                exchange -> respond(exchange, "SECTION"));
        server.createContext("/api/admin/",
                exchange -> respond(exchange, "ADMIN"));
        server.createContext("/Api/",
                exchange -> respond(exchange, "CAPITAL"));
        server.createContext("/v1",
                exchange -> respond(exchange, "VERSION"));
        server.setExecutor(workers);
        server.start();
        try {
            HttpClient client = HttpClient.newHttpClient();
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            test(client, base, "/api");
            test(client, base, "/apiX");
            test(client, base, "/api/");
            test(client, base, "/api/items");
            test(client, base, "/api/admin/status");
            test(client, base, "/api/Admin/status");
            test(client, base, "/Api/items");
            test(client, base, "/API/items");
            test(client, base, "/v123");
            test(client, base, "/api/item?sort=asc");
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Biên dịch/chạy với Java 17+:

```sh
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 PathPrefixRoutingDemo.java
java --add-modules jdk.httpserver PathPrefixRoutingDemo
```

Stdout đã kiểm chứng:

```text
/api => 200/BASE@/api
/apiX => 200/BASE@/api
/api/ => 200/SECTION@/api/
/api/items => 200/SECTION@/api/
/api/admin/status => 200/ADMIN@/api/admin/
/api/Admin/status => 200/SECTION@/api/
/Api/items => 200/CAPITAL@/Api/
/API/items => 404/NO_CONTEXT
/v123 => 200/VERSION@/v1
/api/item?sort=asc => 200/SECTION@/api/
```

Giải thích những dòng quan trọng:

1. `/apiX` vào context `/api`: **prefix collision** với path không cùng REST segment.
2. `/api/` và `/api/items` vào context `/api/` vì nó dài hơn `/api`.
3. `/api/admin/status` vào `/api/admin/` theo longest matching prefix.
4. `/api/Admin/status` rơi về `/api/`; case mismatch ở child context **không chặn parent**.
5. `/Api/items` khớp context riêng có chữ `A` hoa; `/API/items` không khớp context nào và trả 404 khi không có root fallback.
6. `/v123` vào `/v1` do literal string prefix.
7. Query `?sort=asc` không thay context được chọn.

Ứng dụng phải validate path và quyền ở tầng business; test này minh họa **routing** chứ không cấp xác thực hoặc bảo đảm an ninh. Nó đóng responses/exchanges, dọn `HttpServer` và executor, không truy cập Internet.

## 13. Java 17 runnable demo 2: kiểm tra segment, encoded alias và method

Tệp **`StrictPathGuardDemo.java`** đăng ký context rộng `"/docs"`, nhưng chỉ cho `GET /docs` hoặc `GET /docs/<single-lowercase-ascii-slug>`. Các paths `/docs-public`, `/docs/%61dmin`, `/docs/a/b` bị handler từ chối. `/Docs/a1` không khớp context và bị server trả 404. `POST` trả 405 với `Allow: GET`.

```java
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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class StrictPathGuardDemo {
    private static void reply(HttpExchange exchange, int status,
                              String body) throws IOException {
        try (exchange) {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    private static HttpResponse<String> request(HttpClient client,
            String base, String path, String method) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                URI.create(base + path)).timeout(Duration.ofSeconds(5));
        HttpRequest call = "GET".equals(method)
                ? builder.GET().build()
                : builder.POST(HttpRequest.BodyPublishers.noBody()).build();
        return client.send(call, HttpResponse.BodyHandlers.ofString());
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        AtomicInteger boundaryDenied = new AtomicInteger();
        AtomicReference<String> encodedRaw = new AtomicReference<>();
        AtomicReference<String> encodedDecoded = new AtomicReference<>();

        server.createContext("/docs", exchange -> {
            URI requestURI = exchange.getRequestURI();
            String raw = requestURI.getRawPath();
            if (raw.contains("%")) {
                encodedRaw.set(raw);
                encodedDecoded.set(requestURI.getPath());
            }
            if (!"GET".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "GET");
                reply(exchange, 405, "METHOD");
                return;
            }
            // One deliberately narrow application route:
            // /docs or /docs/<one lowercase ASCII slug>.
            boolean accepted = "/docs".equals(raw)
                    || raw.matches("/docs/[a-z0-9-]+");
            if (!accepted) {
                boundaryDenied.incrementAndGet();
                reply(exchange, 404, "REJECTED");
                return;
            }
            reply(exchange, 200, "DOC:" + raw);
        });
        server.setExecutor(workers);
        server.start();

        try {
            HttpClient client = HttpClient.newHttpClient();
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpResponse<String> root = request(
                    client, base, "/docs", "GET");
            HttpResponse<String> item = request(
                    client, base, "/docs/a1", "GET");
            HttpResponse<String> prefix = request(
                    client, base, "/docs-public", "GET");
            HttpResponse<String> encoded = request(
                    client, base, "/docs/%61dmin", "GET");
            HttpResponse<String> nested = request(
                    client, base, "/docs/a/b", "GET");
            HttpResponse<String> uppercase = request(
                    client, base, "/Docs/a1", "GET");
            HttpResponse<String> query = request(
                    client, base, "/docs/a1?view=full", "GET");
            HttpResponse<String> method = request(
                    client, base, "/docs/a1", "POST");

            System.out.println("Exact /docs: " + root.statusCode());
            System.out.println("Single slug: " + item.statusCode());
            System.out.println("Prefix collision rejected: "
                    + prefix.statusCode() + "/" + prefix.body());
            System.out.println("Encoded slug rejected: "
                    + encoded.statusCode() + "/" + encoded.body());
            System.out.println("Nested path rejected: "
                    + nested.statusCode());
            System.out.println("Case mismatch: "
                    + uppercase.statusCode());
            System.out.println("Query does not select context: "
                    + query.statusCode());
            System.out.println("Method rejected: "
                    + method.statusCode());
            System.out.println("Encoded raw path: "
                    + encodedRaw.get());
            System.out.println("Decoded URI path: "
                    + encodedDecoded.get());
            System.out.println("Handler denials: "
                    + boundaryDenied.get());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Chạy:

```sh
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 StrictPathGuardDemo.java
java --add-modules jdk.httpserver StrictPathGuardDemo
```

Stdout đã kiểm thử:

```text
Exact /docs: 200
Single slug: 200
Prefix collision rejected: 404/REJECTED
Encoded slug rejected: 404/REJECTED
Nested path rejected: 404
Case mismatch: 404
Query does not select context: 200
Method rejected: 405
Encoded raw path: /docs/%61dmin
Decoded URI path: /docs/admin
Handler denials: 3
```

Điểm cần hiểu:

- `/docs-public` **đã đi vào context `/docs`**, nên nhận `404/REJECTED` do handler, khác với `/Docs/a1` nhận core server 404 do không có context.
- `/docs/%61dmin` không được chấp nhận theo policy **raw spelling** của demo; `getPath()` vẫn decode nó thành `/docs/admin`.
- `/docs/a/b` không đáp ứng quy tắc đúng một slug.
- `?view=full` không làm đổi context selection; handler vẫn cần validate query nếu API sử dụng nó.
- `POST /docs/a1` đi vào context `/docs` rồi bị application method guard từ chối 405.
- `Handler denials: 3` xác nhận ba path không chuẩn đã **bị guard xử lý**, không phải tự biến mất do mạng.

**Giới hạn demo:** chỉ một tài nguyên tưởng tượng và slug ASCII; không phải authentication/authorization production, không xử lý file paths, Unicode identifiers, proxies hay symlink attacks. Không dùng regex này để bảo vệ mọi API mà chưa phân tích canonical resource identity.

## 14. Đặt authorization đúng vị trí khi có parent/child context

Có thể cấu hình:

```java
// Snippet minh họa: filter đã được triển khai.
HttpContext admin = server.createContext(
        "/api/admin/", adminHandler);
admin.getFilters().add(authFilter);
server.createContext("/api/", publicHandler);
```

Khi request `/api/Admin/status` tới, Java 17 chọn **`/api/`**, chứ không chọn `/api/admin/`. Filter của admin context **không chạy** vì request không thuộc context ấy. Nếu `publicHandler` tự lowercase path rồi truy cập dữ liệu admin, đó là **authorization bypass do ứng dụng**.

Để tránh:

1. Guard canonical path và case tại ingress/dispatcher, từ chối các aliases không hợp lệ.
2. Luôn kiểm tra **principal và quyền trên resource** trong business layer, không chỉ ở context filter.
3. Tránh fallback public diễn giải request bị từ chối theo cách khác.
4. Đặt filters đúng contexts và test parent fallback.
5. Log context thực sự được chọn bằng `getHttpContext().getPath()`, canonical route ID và authz outcome.

`Filter` và `Authenticator` là các building blocks. Một hệ thống đa tenant có auth/session/roles phức tạp nên cân nhắc framework/router đã kiểm chứng, thay vì tự tập hợp các prefix guards rời rạc.

## 15. Method 405, 404 và lifecycle đúng

`HttpContext` không chọn route theo method. Nếu handler chỉ hỗ trợ GET, nó nên trả 405 và header `Allow: GET`:

```java
// Snippet trong HttpHandler.handle, không phải class độc lập.
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    exchange.sendResponseHeaders(405, -1);
    exchange.close();
    return;
}
```

Theo Java 17 `HttpExchange.sendResponseHeaders(status,length)`:

- `length > 0`: phải ghi **đúng số bytes** response.
- `length == 0`: sử dụng chunked transfer encoding, **không** có nghĩa “zero-byte response”.
- `length == -1`: response **không có body**.

Đừng chỉ gọi `return` mà không kết thúc exchange; đóng response stream và request stream hoặc `try(exchange)` trong mọi đường xử lý. Ví dụ 1 và 2 đều dùng `try(exchange)` trong hàm trả response.

Status 404 có thể chỉ path không hợp lệ, route không tồn tại hoặc resource không được phép lộ sự tồn tại; 403 là quyền bị từ chối, 401 là thiếu authn. Chọn status theo security/API contract, không coi 404 là một authentication mechanism.

## 16. Không dùng route literal làm đường dẫn filesystem trực tiếp

Một handler phục vụ file thường gặp lỗi:

```java
// Anti-pattern: minh họa cách không được tin URL path.
Path file = root.resolve(exchange.getRequestURI()
        .getPath().substring("/files/".length()));
// Nếu thiếu containment/symlink checks, có thể traversal.
```

Cần xác định route canonical, giải mã đúng một lần, từ chối dot segments/encoded separators không được phép, xác nhận resolved/canonical file nằm trong storage root được cấp quyền **sau khi normalize và xét symlinks**, rồi kiểm tra authz trên file/resource ID. Không áp `String.startsWith(root.toString())` như một phép kiểm tra containment an toàn cho filesystem.

Nếu reverse proxy/WAF thực hiện rewrite/normalize khác backend, phải test **đúng chuỗi proxy → `HttpServer` → app**. Một request `/docs/%2e%2e/admin` có thể trông khác ở từng tầng. Không mặc định mọi proxy bảo vệ được ứng dụng khỏi encoded aliases.

## 17. Thiết kế router nhỏ không phụ thuộc prefix collision

Với ứng dụng rất nhỏ, hai kiểu an toàn hơn là:

**A. Đăng ký chính xác root và descendants, có guard:**

```java
server.createContext("/api", apiRoot);
server.createContext("/api/", apiChildren);
```

`apiRoot` phải reject `/apiX`. `apiChildren` phải parse segments và authz từng operation.

**B. Một context prefix, dispatcher nội bộ có contract:**

```java
server.createContext("/api", dispatcher);
```

`dispatcher` nhận raw URI, canonicalize/validate đúng policy, check method + path shape + identity, rồi gọi handler cụ thể. Đừng để mỗi business handler decode/lowercase khác nhau.

Khi có nhiều routes template như `GET /users/{id}`, `POST /orders/{id}/items`, auth per route, content negotiation, middleware hoặc dynamic APIs, framework/router với model route rõ ràng thường giảm rủi ro hơn xây hàng trăm `startsWith`.

## 18. Không được coi {id} là wildcard trong createContext

`createContext("/users/{id}", handler)` **không tự tạo một path parameter**. Trong `HttpServer` Java 17, đây chỉ là một literal context path chứa các ký tự `{` và `}`. Request `/users/42` sẽ không tự thay thế `{id}`.

Muốn nhận `/users/42`, đăng ký `"/users/"` rồi tự parse suffix sau khi đã xác thực boundary và canonicalization:

```java
// Snippet minh họa: cần xử lý status, authz và exceptions.
String raw = exchange.getRequestURI().getRawPath();
if (!raw.startsWith("/users/")) {
    // reject
}
String idText = raw.substring("/users/".length());
if (!idText.matches("[0-9]{1,18}")) {
    // reject
}
```

Parse `idText` phải kiểm tra số lớn tràn và authorization theo resource ID. Đừng coi regex pass là quyền truy cập. Nếu route có nhiều lồng ghép, tốt hơn dùng một router có parser/path-template model và tests bảo mật.

## 19. Quy tắc case-sensitive và HTTP header không mâu thuẫn

Tên HTTP headers như `Content-Type` và `content-type` là case-insensitive. Còn URI path có identity riêng và trong `HttpServer` Java 17 **context paths case-sensitive**. Vì vậy `/api/Admin` và `/api/admin` không đồng nghĩa, trừ khi **ứng dụng chủ động thiết kế** chúng là aliases.

Nếu chọn route case-insensitive cho sản phẩm:

- Quy định canonical spelling cho resource lúc tạo.
- Tạo unique constraint/namespace để không có `ReportA` và `reporta` mâu thuẫn.
- Canonicalize nhất quán trước authorization, caching và storage lookup.
- Dùng Unicode normalization/case folding đúng với yêu cầu ngôn ngữ khi có non-ASCII identifiers.
- Kiểm thử cùng policy từ gateway/proxy đến backend.
- Trả redirect/404 theo contract, tránh tự sửa nguy hiểm với methods có side effects.

Không dùng `toLowerCase()` một cách tùy tiện trong từng handler và không nhầm việc hỗ trợ Unicode URL với cho phép mọi kiểu mã hóa không chuẩn.

## 20. Kế hoạch kiểm thử route có dữ liệu nhạy cảm

Ít nhất cần các ca:

1. `/admin`, `/admin/`, `/admin/users` — xác định chính xác root/trailing slash/descendants.
2. `/administrator`, `/admin-old` — prefix collision.
3. `/Admin`, `/ADMIN`, `/api/Admin/users` — case mismatch và fallback.
4. `/admin/%61`, `/admin/%2fsecret`, `/admin/%2e%2e/secret` — encoded aliases.
5. `/admin/%252e%252e` — double encoding.
6. `/admin/./users`, `/admin/../public` — dot segments; kiểm thử qua client và proxy thật.
7. `/admin//users` — repeated slashes.
8. Query khác nhau, header variants, GET/POST/PUT/DELETE/HEAD — method/query independence.
9. Có/không root fallback — 404 do server vs 404 do handler.
10. Authn/authz: user thường không thể truy cập resource admin qua path alias hay fallback.
11. Path params: slug quá dài, Unicode/UTF-8 không chuẩn, null bytes, encoded separators.
12. URI → filesystem: canonical path, containment, symlink, tenant boundary.
13. Quan sát `getHttpContext().getPath()` và app route ID trong logs.
14. Khi nâng JDK/provider: chạy lại route-match tests và xem thay đổi semantics.

**Không kiểm thử chỉ happy path** như `GET /api/admin/status` rồi kết luận router an toàn. Phần lớn lỗi xuất hiện ở các aliases và đường fallback.

## 21. Tài nguyên, logging và vận hành liên quan

Routing đúng vẫn có thể thất bại khi tải nặng. `HttpServer` dùng callback handler có thể block trên input, DB và response output. Cần `setExecutor` trước `start()`, request body size cap, connection/timeouts, bounded queues và cleanup. `Executors.newFixedThreadPool(n)` **không tự tạo queue bounded**; nó chỉ hạn chế số workers đang chạy.

Logging hữu ích gồm: raw path đã redacted, selected context, canonical route name, method, response status, request ID, principal/tenant ID và authorization outcome. Không log full query string nếu chứa token/PII, không tin mọi `X-Forwarded-*` header từ clients.

Đếm riêng `path_policy_rejected` và `router_fallback` để sớm thấy requests `/api/Admin/*` rơi sai context. Nếu app có HTTP reverse proxy, tests và logs phải xác minh request URI đã bị rewrite/normalize ra sao trước khi đến Java handler.

Nếu router cần nhiều path templates, chuẩn hóa Unicode, method-aware routing, auth middleware và observability, hãy so tổng chi phí tự triển khai với framework/server chuyên dụng thay vì chỉ so số dòng code.

## 22. Các lỗi phổ biến và cách sửa

1. **Tưởng `"/api"` chỉ match `/api`.** Sai: `/apiX` cũng có thể khớp.
2. **Tưởng `"/api/"` match `/api`.** Sai: slash cuối là một ký tự của prefix.
3. **Tưởng context đăng ký đầu tiên thắng.** Sai: longest matching prefix.
4. **Tưởng path case-insensitive như HTTP header.** Sai: Java 17 match literal case-sensitive.
5. **Tưởng child filter bảo vệ mọi alias của admin.** Sai: nếu request rơi về parent, filter child không chạy.
6. **Tưởng root `"/"` chỉ nhận request `/`.** Sai: nó có thể catch-all.
7. **Tưởng `"/users/{id}"` là template.** Sai: đó là literal string trong context path.
8. **Tưởng query làm thay đổi context selection.** Sai: matching dùng URI path.
9. **Tưởng GET/POST là hai contexts riêng khi path giống nhau.** Sai nếu không có app router.
10. **Tưởng `getRawPath` luôn bằng `getPath`.** Sai với percent encoding.
11. **Decode một path nhiều lần cho “đúng”.** Có thể gây traversal/authorization mismatch.
12. **Lowercase mọi path trước authz.** Có thể gộp nhầm resources/tenant keys.
13. **Chỉ kiểm tra `startsWith("/docs")`.** Không phân biệt `/docs-public`.
14. **Dùng regex slug như thể đã đủ authn/authz.** Không có principal/resource permission.
15. **Mở file theo raw URI path chưa kiểm soát.** Có path traversal/symlink risks.
16. **Để public fallback parse secret routes.** Cần 404/canonical guard + authz.
17. **Không đóng HttpExchange khi trả 404/405.** Dễ treo client/rò resources.
18. **Hiểu `sendResponseHeaders(404,0)` là no body.** Java 17: 0 là chunked, -1 là no body.
19. **Chỉ test direct localhost, bỏ proxy rewrites.** Cần end-to-end test.
20. **Giả định mọi JDK/provider tương lai có hoàn toàn cùng chi tiết routing.** Pin phiên bản và chạy regression tests.

## 23. Câu hỏi tự kiểm tra

**1.** Với contexts `"/api"` và `"/api/"`, `/api/items` vào cái nào? **`"/api/"`**, prefix dài hơn.

**2.** Chỉ có `"/v1"` thì `/v123` có thể vào context đó không? **Có theo Java 17** vì prefix literal.

**3.** `/api/Admin/status` có vào context `"/api/admin/"` không? **Không**; nếu `"/api/"` tồn tại thì có thể rơi về context cha.

**4.** `/API/status` và `/api/status` có giống nhau không? **Không**, case-sensitive.

**5.** Tạo root context `"/"` có làm unknown paths tự luôn 404 không? **Không**, root handler được chọn và phải quyết định.

**6.** `?sort=asc` có ảnh hưởng lựa chọn context không? **Không**, query không tham gia prefix path matching.

**7.** `GET` và `POST` tới cùng URI path có được core server tự phân handler không? **Không**; ứng dụng xét method.

**8.** `getRawPath()` của `/docs/%61dmin` trả gì? **`/docs/%61dmin`**; `getPath()` cho `/docs/admin`.

**9.** Tại sao `/docs-public` trong demo trả `404/REJECTED`? **Nó khớp context `/docs`, nhưng handler có segment guard từ chối.**

**10.** Filter gắn context `/api/admin/` có chạy với `/api/Admin/` không? **Không** nếu request được chọn vào context khác.

**11.** Có nên dùng `toLowerCase` cho mọi path để tránh 404 không? **Không**; cần canonical route/resource policy rõ.

**12.** Trong `sendResponseHeaders(status,length)`, length bằng `-1` nghĩa gì? **Không có response body**.

**13.** Việc route match đúng đã đủ an toàn để đọc file theo path chưa? **Chưa**; phải kiểm tra canonical filesystem path, symlink và authorization.

**14.** Khi nào nên dùng HTTP router/framework khác? **Khi cần nhiều method/path templates, middleware/security integration và normalization có contract rõ hơn mức literal-prefix.**

## 24. Checklist trước khi triển khai

- [ ] Chốt chính xác **longest literal prefix, case-sensitive** của Java 17.
- [ ] Kiểm thử `/api`, `/api/`, `/apiX` và các descendants.
- [ ] Kiểm thử chữ hoa/chữ thường ở cả parent và child contexts.
- [ ] Không coi context prefix là REST path-template hoặc authorization.
- [ ] Quy định route canonical và raw/decoded URI policy thống nhất.
- [ ] Không decode hai lần; có chính sách encoded slash, dots, Unicode và duplicate slashes.
- [ ] Kiểm tra ranh giới path segments, không chỉ string prefix.
- [ ] Phân biệt 404 core, 404 handler, 405 method và 403 authorization.
- [ ] Các filters/authenticators áp đúng contexts; fallback không bỏ qua authz.
- [ ] Có validation, size cap, bounded executor, deadline và `HttpExchange` cleanup.
- [ ] Có kiểm thử qua reverse proxy/WAF và nâng cấp JDK/provider.
- [ ] Có structured logs redacted cho selected context, canonical route, principal và outcome.

**Kết luận:** Trong `HttpServer` Java 17, **context selection chỉ là phép chọn prefix literal dài nhất**, không thay thế một application router và càng không thay thế authorization. Dấu `/`, chữ hoa/chữ thường, percent encoding và parent fallback phải được kiểm tra độc lập. Muốn một route tin cậy, cần **canonical path policy + segment guards + method handling + authz + negative tests**; nếu yêu cầu định tuyến phức tạp, hãy cân nhắc framework/router chuyên dụng thay vì tự viết chuỗi `startsWith` ngày càng khó kiểm soát.

### Nguồn chính thức

- [Java SE 17 — HttpServer, Mapping request URIs to HttpContext paths](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [Java SE 17 — HttpContext, filters and authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html)
- [Java SE 17 — HttpExchange, getRequestURI, getHttpContext, response lifetime](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
- [Java SE 17 — URI, getPath and getRawPath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html)
- [Java SE 17 — jdk.httpserver package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html)
- [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html).