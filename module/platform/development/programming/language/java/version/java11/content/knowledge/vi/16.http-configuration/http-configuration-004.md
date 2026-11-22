# `Authenticator` và thông tin xác thực khi cấu hình Java HTTP Client (Java 11 trở lên)

## 1. Bài toán: ai có quyền truy cập endpoint HTTP?

Trong một ứng dụng Java, không phải endpoint HTTP nào cũng là tài nguyên công khai. Một API có thể yêu cầu xác thực bằng tài khoản/mật khẩu, proxy trong doanh nghiệp có thể yêu cầu tài khoản riêng, hoặc một dịch vụ sử dụng access token. Khi phía nhận chưa có thông tin xác thực hợp lệ, nó có thể trả về HTTP `401 Unauthorized` hoặc `407 Proxy Authentication Required` kèm một **authentication challenge**.

Java 11 đã chuẩn hóa HTTP Client trong module `java.net.http`. Một cấu hình liên quan đến xác thực là:

```java
import java.net.Authenticator;
import java.net.http.HttpClient;

HttpClient client = HttpClient.newBuilder()
        .authenticator(myAuthenticator)
        .build();
```

Ở đây, `myAuthenticator` là instance của `java.net.Authenticator` mà ứng dụng tự triển khai hoặc cung cấp. Nó có trách nhiệm **trả thông tin xác thực khi HTTP client cần**, không tự tạo user session, không phân quyền dữ liệu và không thay thế bảo mật TLS.

Phân biệt ngay từ đầu:

- **Authentication (xác thực):** chứng minh danh tính hoặc quyền sử dụng một credential trước server/proxy.
- **Authorization (phân quyền):** xác định danh tính đã xác thực có được làm hành động cụ thể hay không.
- **`Authenticator`:** API Java hỗ trợ lấy username/password theo challenge.
- **`Authorization`:** tên **HTTP request header** thường gửi credential cho server, có thể mang Basic hoặc Bearer token tùy giao thức.
- **`Proxy-Authorization`:** HTTP request header riêng cho xác thực **proxy**.
- **HTTPS/TLS:** bảo vệ thông tin khi truyền, không đồng nghĩa ứng dụng đã được cấp quyền gọi API.

**Trọng tâm bài này:** `HttpClient.Builder.authenticator(Authenticator)`, `PasswordAuthentication`, Basic authentication challenge, phân biệt server/proxy, quản lý credential an toàn và khi nào phải chủ động gửi `Authorization` thay vì dùng `Authenticator`. Những API này có trong Java 11 và vẫn được hỗ trợ ở các JDK hiện hành.

## 2. Cơ chế HTTP challenge-response: `401` và `407`

### 2.1. Server authentication: HTTP 401

Một lần trao đổi HTTP Basic authentication thường diễn ra theo mô hình:

```text
Java HttpClient                      API server
      |                                  |
      | GET /private                     |
      |--------------------------------->|
      |                                  |
      | 401 Unauthorized                 |
      | WWW-Authenticate: Basic          |
      |                   realm="demo"   |
      |<---------------------------------|
      |                                  |
      | HttpClient hỏi Authenticator     |
      | → PasswordAuthentication         |
      |                                  |
      | GET /private                     |
      | Authorization: Basic <base64>    |
      |--------------------------------->|
      |                                  |
      | 200 OK                           |
      |<---------------------------------|
```

Đây là sơ đồ **đơn giản hóa một lần thử xác thực**. Trên một client đã có trạng thái xác thực cho cùng scope, implementation có thể tái sử dụng thông tin theo cơ chế của nó; không nên dùng số lượng request thực tế làm một hợp đồng cố định.

Các thành phần:

- `401 Unauthorized`: server yêu cầu **authentication** hoặc thông tin đã nhận không hợp lệ.
- `WWW-Authenticate`: response header giới thiệu phương thức xác thực, ví dụ `Basic realm="demo"`.
- `Basic`: authentication scheme trong HTTP, không phải tên protocol `http`/`https`.
- `realm`: gợi ý miền bảo vệ được server công bố; phải xem là thông tin của challenge, không phải một bí mật.
- `Authorization`: request header chứa thông tin xác thực của **server**; chỉ được gửi đến endpoint và phạm vi tin cậy đã xác định.

Một response `401` **không tự làm thành công request**: Java chỉ có thể lấy credential và thử lại theo khả năng của implementation và authentication scheme được hỗ trợ. Nếu credential sai hoặc server không chấp nhận, response vẫn có thể là `401` hoặc quá trình gửi có thể lỗi. Caller vẫn phải kiểm tra `response.statusCode()`.

### 2.2. Proxy authentication: HTTP 407

Khi sử dụng HTTP proxy, một challenge có thể xuất phát từ proxy:

```text
Java HttpClient                  HTTP proxy                     Server
     |                              |                             |
     | request qua proxy            |                             |
     |----------------------------->|                             |
     | 407 Proxy Authentication     |                             |
     | Proxy-Authenticate: Basic    |                             |
     |<-----------------------------|                             |
     | Authenticator: PROXY         |                             |
     | Proxy-Authorization ...      |                             |
     |----------------------------->|  chuyển tiếp theo protocol  |
     |                              |---------------------------->|
```

Cặp header `Proxy-Authenticate`/`Proxy-Authorization` là **của proxy**, khác `WWW-Authenticate`/`Authorization` của origin server.

| Tình huống | Phía yêu cầu credential | Response status | Challenge header | Request credential header | Loại callback |
| --- | --- | --- | --- | --- | --- |
| Server yêu cầu xác thực | Origin server | `401` | `WWW-Authenticate` | `Authorization` | `Authenticator.RequestorType.SERVER` |
| Proxy yêu cầu xác thực | Proxy | `407` | `Proxy-Authenticate` | `Proxy-Authorization` | `Authenticator.RequestorType.PROXY` |

Một ứng dụng có thể sử dụng proxy nhưng không cần credential để truy cập origin server; cũng có thể phải xác thực **cả hai** bằng credential **khác nhau**. Không tái sử dụng username/password của server làm mật khẩu proxy một cách mặc định.

### 2.3. `403 Forbidden` khác `401`

`403 Forbidden` thường có nghĩa server hiểu yêu cầu nhưng từ chối thực hiện theo chính sách quyền truy cập. Nó **không tự yêu cầu** `Authenticator` cung cấp credential mới. Trong thực tế, server có thể dùng status theo cách riêng, nhưng về mô hình HTTP chuẩn:

- `401` + challenge: có thể cần hoặc cần sửa thông tin xác thực;
- `403`: thường là vấn đề **quyền** hoặc chính sách server;
- `407` + proxy challenge: cần hoặc cần sửa credential của proxy;
- `200` hoặc status thành công khác: vẫn phải kiểm tra nội dung response theo contract.

**Không coi mọi `4xx` là tín hiệu nhập lại mật khẩu**, và không coi `Authenticator` là giải pháp cho `403`, `429` hoặc `5xx`.

## 3. Các API Java quan trọng và trách nhiệm của từng thành phần

| API | Được dùng làm gì? | Điểm cần nhớ |
| --- | --- | --- |
| `HttpClient.newBuilder()` | Tạo bộ cấu hình client | Builder có thể thiết lập authenticator, proxy, timeout, redirect... |
| `HttpClient.Builder.authenticator(auth)` | Gắn `Authenticator` cho HTTP client | Áp dụng ở phạm vi client, không phải tham số riêng của từng `HttpRequest` |
| `java.net.Authenticator` | Cung cấp callback lấy credential theo requestor | Thường override `getPasswordAuthentication()` |
| `java.net.PasswordAuthentication` | Mang username và `char[]` password | Trả từ callback để HTTP client xử lý phương thức xác thực |
| `getRequestorType()` | Phân biệt SERVER/PROXY | Giữ hai bộ credential ở phạm vi riêng |
| `getRequestingHost()/getRequestingPort()` | Xác định đích yêu cầu credential | Nên kiểm tra allowlist trước khi trả secret |
| `getRequestingScheme()` | Authentication scheme, ví dụ Basic | **Không phải** URI scheme `https` |
| `getRequestingProtocol()` | Protocol đang yêu cầu xác thực | Thường là `http` hoặc `https` trong HTTP |
| `getRequestingPrompt()` | Prompt/realm từ bên yêu cầu | Có thể dùng như điều kiện ràng buộc scope |
| `HttpRequest.Builder.header(...)` | Đặt `Authorization` khi API yêu cầu token/header thủ công | Không phải mọi phương thức auth đều qua `Authenticator` |
| `HttpResponse.statusCode()` | Kiểm tra response status | Bắt buộc kể cả khi đã cấu hình authenticator |

### `Authenticator` là lớp callback, không phải kho credential vạn năng

Chữ ký override:

```java
import java.net.Authenticator;
import java.net.PasswordAuthentication;

Authenticator auth = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        // Chỉ trả credential khi phù hợp requestor/scope.
        return null;
    }
};
```

Đây là **mã khung**: `null` nghĩa là không cung cấp credential. Trong ứng dụng thật, callback nên xác định **ai đang yêu cầu** trước khi quyết định trả username/password tương ứng.

API `getPasswordAuthentication()` không nhận trực tiếp tham số, nhưng subclass có thể gọi các phương thức protected để truy cập context của challenge. Một số trường như host, URL hoặc site có thể là `null` khi không có thông tin. Không viết code mặc định rằng chúng chắc chắn luôn tồn tại.

`HttpClient.Builder.authenticator(auth)` giúp **client cụ thể** dùng authenticator đó. Java cũng có `Authenticator.setDefault(...)` ở cấp JVM nhưng không cần dùng cho tình huống này: cấu hình **per-client** rõ ràng hơn, tránh bất ngờ ảnh hưởng các kết nối khác trong tiến trình.

### `PasswordAuthentication` và password dạng `char[]`

`PasswordAuthentication` mang username và password dưới dạng mảng ký tự:

```java
PasswordAuthentication credential =
        new PasswordAuthentication(
                "lesson-user",
                "lesson-pass".toCharArray());
```

Đây chỉ là credential **giả dùng cho bài test**. Trong production:

- Không hard-code mật khẩu thật trong source, test artifact, command line hoặc URL.
- Tải credential từ secret manager, nguồn cấu hình bảo vệ hoặc cơ chế cấp token được phê duyệt.
- Chỉ cấp credential đúng host/proxy/realm và quyền tối thiểu.
- Không in username/password, `Authorization`, `Proxy-Authorization` hoặc request body chứa secret vào log.
- Bảo vệ, rotate và thu hồi secret theo chính sách. Dùng `char[]` có thể hỗ trợ kiểm soát một số bản sao trong bộ nhớ, nhưng **không bảo đảm secret không từng được copy** vào đối tượng/runtime khác.

## 4. Viết authenticator có kiểm tra đúng phạm vi

Sai lầm nguy hiểm là **trả cùng một username/password cho mọi challenge**:

```java
// KHÔNG NÊN dùng cho nhiều endpoint hoặc proxy không tin cậy.
Authenticator tooBroad = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        return new PasswordAuthentication(user, password);
    }
};
```

Đây là code **minh họa bên trong phương thức** với `user`/`password` đã khai báo. Nó không xác minh nguồn yêu cầu credential. Nếu client đi qua redirect hoặc proxy bất ngờ, chính sách cấp credential quá rộng có thể gây lộ secret.

Thay vào đó, kiểm tra ít nhất:

1. `getRequestorType()` có phải `SERVER` hay `PROXY` đúng như mong đợi?
2. `getRequestingHost()` có nằm trong allowlist chính xác? Với một endpoint bảo vệ tốt nhất so sánh hostname literal dự kiến.
3. `getRequestingPort()` có đúng port đã cấu hình?
4. `getRequestingScheme()` có thuộc scheme được ứng dụng hỗ trợ, ví dụ `Basic`?
5. `getRequestingPrompt()` (realm) có nằm trong phạm vi được chấp nhận nếu API công bố realm?
6. URI scheme/transport có đúng chính sách an toàn, đặc biệt **HTTPS** khi gửi Basic trên Internet?

Ví dụ có kiểm tra scope:

```java
static final class ScopedAuthenticator extends Authenticator {
    private final String allowedHost;
    private final int allowedPort;
    private final String allowedRealm;
    private final String username;
    private final char[] password;

    ScopedAuthenticator(
            String allowedHost,
            int allowedPort,
            String allowedRealm,
            String username,
            char[] password) {
        this.allowedHost = allowedHost;
        this.allowedPort = allowedPort;
        this.allowedRealm = allowedRealm;
        this.username = username;
        this.password = password.clone();
    }

    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        if (getRequestorType() != RequestorType.SERVER) {
            return null;
        }

        if (!allowedHost.equalsIgnoreCase(getRequestingHost())
                || getRequestingPort() != allowedPort
                || !"basic".equalsIgnoreCase(getRequestingScheme())
                || !allowedRealm.equals(getRequestingPrompt())) {
            return null;
        }

        return new PasswordAuthentication(
                username, password.clone());
    }
}
```

Đây là **class hỗ trợ** đặt trong chương trình đã import `java.net.Authenticator` và `java.net.PasswordAuthentication`. Khi dùng thực tế, khởi tạo với secret từ nguồn an toàn, quản lý vòng đời/xóa bản sao theo chính sách và giới hạn client chỉ gửi đến endpoint được phép. Ví dụ ở đây tập trung vào phân quyền callback, không triển khai secret manager.

**Lưu ý:** kiểm tra host/port/realm trong callback là một lớp phòng vệ, **không thay thế** validate URL đầu vào, kiểm soát redirect, xác minh TLS certificate, chính sách proxy và quản lý secret. Authentication scheme `Basic` không cung cấp khả năng "mã hóa secret" riêng.

## 5. Khi nào callback được gọi? Basic là cơ chế phản hồi challenge

Với Basic authentication:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo"
```

HTTP Client có thể nhận challenge và hỏi `Authenticator` để lấy credential. Với JDK HTTP Client tích hợp, đường xử lý tự động này hướng tới HTTP Basic authentication; **không nên giả định `Authenticator` hiểu mọi scheme**, đặc biệt Digest/NTLM/Kerberos/OAuth2/JWT/Bearer nếu chưa đối chiếu khả năng của implementation và yêu cầu của server.

Trong Java SE 26, implementation note của `HttpClient.Builder.authenticator` nêu rõ hiện tại implementation tích hợp hỗ trợ HTTP **Basic**. Khi API yêu cầu cơ chế khác, nên dùng trình xác thực/SDK chuyên dụng phù hợp hoặc tự xây `Authorization` theo giao thức đã thống nhất; không mong một callback `PasswordAuthentication` tự biến mật khẩu thành OAuth token.

### Basic header thực chất chứa gì?

Theo RFC 7617, với tài khoản `lesson-user` và password `lesson-pass` chỉ chứa ASCII, giá trị chứng thực Basic là:

```text
Base64(ASCII("lesson-user:lesson-pass"))
```

Request header tương ứng:

```http
Authorization: Basic <base64-of-username-colon-password>
```

**Base64 là mã hóa biểu diễn, không phải encryption.** Người nhận hoặc người quan sát được header có thể giải Base64 trở lại user/password. Vì thế:

- Trong production, dùng **HTTPS** với xác minh chứng chỉ TLS đầy đủ; không gửi Basic qua HTTP thuần trên mạng không tin cậy.
- Không ghi header Authorization vào log, telemetry hay lỗi exception công khai.
- Tránh Basic credential có phạm vi quá rộng. Một user/password dùng cho nhiều hệ thống làm tăng phạm vi thiệt hại nếu lộ.
- Với username/password chứa ký tự không phải ASCII, charset của Basic cần được xác định theo khả năng và contract phía server (RFC 7617 có tham số `charset`); không tự giả định mọi bên hiểu Unicode giống nhau. Ví dụ chương trình dùng ASCII để kết quả có thể kiểm thử ổn định.

Sử dụng `Authenticator` cho Basic giúp HTTP Client xử lý nhiều chi tiết challenge/retry. Tuy nhiên, phải xem đây là authentication theo **credential được cấp trong một scope**, không phải một cơ chế session hoặc token rotation đầy đủ.

## 6. Chương trình Java 11+ hoàn chỉnh: server Basic authentication và client có Authenticator

Chương trình sau mô phỏng **HTTP server ở loopback** (`127.0.0.1`), **không truy cập Internet**. Dùng `com.sun.net.httpserver.HttpServer` từ module JDK `jdk.httpserver` chỉ làm fixture kiểm thử; không dùng server này như một production authentication service.

Các endpoint:

- `/secure`: yêu cầu `Authorization: Basic ...` hợp lệ; nếu không có/không đúng thì trả `401` và `WWW-Authenticate: Basic realm="demo"`.
- `/public`: trả `200` không yêu cầu xác thực.
- `/forbidden`: trả `403` không yêu cầu authentication mới.

Test sẽ xác minh: thiếu credentials, Basic challenge qua scoped authenticator, request public, header Authorization được đặt thủ công và `403`.

Lưu toàn bộ chương trình thành **`HttpAuthenticatorDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.Authenticator;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicInteger;

public class HttpAuthenticatorDemo {
    // Chỉ là credential GIẢ của server chạy tại loopback.
    private static final String GOOD_TOKEN = "Basic " +
            Base64.getEncoder().encodeToString(
                    "lesson-user:lesson-pass".getBytes(
                            StandardCharsets.US_ASCII));

    static void respond(HttpExchange exchange, int status, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    static final class ScopedAuthenticator extends Authenticator {
        private final int allowedPort;
        final AtomicInteger callbacks = new AtomicInteger();

        ScopedAuthenticator(int allowedPort) {
            this.allowedPort = allowedPort;
        }

        @Override
        protected PasswordAuthentication getPasswordAuthentication() {
            boolean eligible =
                    getRequestorType() == RequestorType.SERVER &&
                    "127.0.0.1".equals(getRequestingHost()) &&
                    getRequestingPort() == allowedPort &&
                    "basic".equalsIgnoreCase(getRequestingScheme()) &&
                    "demo".equals(getRequestingPrompt());

            if (!eligible) {
                return null;
            }

            callbacks.incrementAndGet();
            return new PasswordAuthentication(
                    "lesson-user", "lesson-pass".toCharArray());
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicInteger protectedRequests = new AtomicInteger();

        server.createContext("/secure", exchange -> {
            protectedRequests.incrementAndGet();
            String authorization =
                    exchange.getRequestHeaders()
                            .getFirst("Authorization");

            if (!GOOD_TOKEN.equals(authorization)) {
                exchange.getResponseHeaders().set(
                        "WWW-Authenticate",
                        "Basic realm=\"demo\"");
                respond(exchange, 401, "AUTH_REQUIRED");
            } else {
                respond(exchange, 200, "PRIVATE_DATA");
            }
        });

        server.createContext("/public",
                exchange -> respond(exchange, 200, "PUBLIC_DATA"));
        server.createContext("/forbidden",
                exchange -> respond(exchange, 403, "FORBIDDEN"));
        server.start();

        try {
            int port = server.getAddress().getPort();
            URI base = URI.create(
                    "http://127.0.0.1:" + port + "/");

            HttpRequest protectedRequest = HttpRequest.newBuilder(
                    base.resolve("secure"))
                    .GET()
                    .build();

            // Client không có authenticator: nhận 401.
            HttpClient noCredentials = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .build();

            HttpResponse<String> initial = noCredentials.send(
                    protectedRequest,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println(
                    "withoutAuth=" + initial.statusCode());

            // Authenticator chỉ cấp password cho server loopback,
            // đúng port, đúng Basic realm.
            ScopedAuthenticator auth =
                    new ScopedAuthenticator(port);

            HttpClient client = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .authenticator(auth)
                    .build();

            HttpResponse<String> granted = client.send(
                    protectedRequest,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println(
                    "withAuth=" + granted.statusCode());
            System.out.println(
                    "body=" + granted.body());
            System.out.println(
                    "callbacks=" + auth.callbacks.get());

            // Endpoint public không cần challenge mới.
            HttpResponse<String> publicResult = client.send(
                    HttpRequest.newBuilder(base.resolve("public"))
                            .GET()
                            .build(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println(
                    "publicStatus=" + publicResult.statusCode());

            // Gắn sẵn Authorization SAI trên request cụ thể.
            String wrongValue = "Basic " +
                    Base64.getEncoder().encodeToString(
                            "lesson-user:wrong".getBytes(
                                    StandardCharsets.US_ASCII));

            HttpRequest manualWrong = HttpRequest.newBuilder(
                    base.resolve("secure"))
                    .header("Authorization", wrongValue)
                    .GET()
                    .build();

            HttpResponse<String> wrong = client.send(
                    manualWrong,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println(
                    "manualWrongStatus=" + wrong.statusCode());
            System.out.println(
                    "callbacksAfterManual=" +
                    auth.callbacks.get());

            HttpResponse<String> forbidden = client.send(
                    HttpRequest.newBuilder(base.resolve("forbidden"))
                            .GET()
                            .build(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println(
                    "forbiddenStatus=" + forbidden.statusCode());
            System.out.println(
                    "protectedRequests=" + protectedRequests.get());
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy bằng JDK 11 hoặc mới hơn:

```bash
javac --release 11 --add-modules jdk.httpserver HttpAuthenticatorDemo.java
java --add-modules jdk.httpserver HttpAuthenticatorDemo
```

**Stdout được kiểm chứng bằng biên dịch `--release 11` và chạy thực tế:**

```text
withoutAuth=401
withAuth=200
body=PRIVATE_DATA
callbacks=1
publicStatus=200
manualWrongStatus=401
callbacksAfterManual=1
forbiddenStatus=403
protectedRequests=4
```

### Phân tích kết quả

1. `withoutAuth=401`: server yêu cầu Basic authentication; client không cung cấp credential nên giữ response `401`.
2. `withAuth=200` và `body=PRIVATE_DATA`: client có `Authenticator` đáp ứng challenge và nhận được dữ liệu được bảo vệ.
3. `callbacks=1`: trong **lần chạy thử này**, callback được gọi một lần cho challenge phù hợp. Không dựa vào con số này để khẳng định mọi implementation/connection luôn callback đúng một lần.
4. `publicStatus=200`: endpoint public trả response bình thường; không cần challenge thêm.
5. `manualWrongStatus=401` và `callbacksAfterManual=1`: request có **`Authorization` đặt sẵn**. Implementation tích hợp dùng header đó và không gọi lại authenticator để "sửa hộ" thông tin không hợp lệ.
6. `forbiddenStatus=403`: server từ chối theo policy; không có tự động chuyển thành một challenge Basic.
7. `protectedRequests=4`: server đã thấy bốn request `/secure` trong kịch bản: request thiếu credential, lượt thử/challenge từ client có authenticator và request đặt thủ công header sai. Giá trị này mô tả **fixture cụ thể**, không phải hợp đồng số lần retry của mọi HTTP client.

### Vì sao ví dụ dùng HTTP thay vì HTTPS?

Vì server chạy trên **loopback của máy test**, sử dụng một tài khoản/mật khẩu giả chỉ để tái hiện quá trình challenge. **Tuyệt đối không sao chép `http://...` cùng Basic credential cho môi trường production.** Với server thực, hãy dùng HTTPS, hostname đã xác thực và quy tắc TLS được hệ thống chấp nhận. Chương trình không xuất credential ra stdout; các header Basic chỉ được so sánh bên trong server nội bộ.

## 7. Request tự đặt `Authorization` có dùng callback không?

Với implementation `HttpClient` tích hợp của JDK hiện hành, Javadoc `HttpClient.Builder.authenticator` nêu:

- Nếu request đã có `Authorization`, **giá trị header đó được sử dụng** cho xác thực tương ứng; `Authenticator` không được gọi để cung cấp credential thay thế cho request đó.
- Nếu request đã có `Proxy-Authorization`, cách xử lý tương tự áp dụng cho xác thực proxy tương ứng.
- Khi header được đặt sẵn mà server/proxy từ chối, lỗi xác thực được trả về ứng dụng; client không tự sửa header rồi retry qua authenticator.

Vì vậy, đừng trộn lẫn hai mô hình một cách thiếu chủ đích:

**Mô hình A — HTTP Basic challenge qua Authenticator:**

```java
HttpClient client = HttpClient.newBuilder()
        .authenticator(scopedAuthenticator)
        .build();

HttpRequest request = HttpRequest.newBuilder(targetUri)
        .GET()
        .build();
// Không đặt Authorization thủ công cho request này.
```

**Mô hình B — chủ động đặt Authorization theo API contract:**

```java
String accessToken = obtainAccessTokenSecurely();

HttpRequest request = HttpRequest.newBuilder(targetUri)
        .header("Authorization", "Bearer " + accessToken)
        .GET()
        .build();
```

Mô hình B dùng ký hiệu `obtainAccessTokenSecurely()` là **hàm của ứng dụng**, không phải Java API có sẵn; đoạn code có tính minh họa. Trong production, token phải đến từ một token provider/SDK hoặc nguồn bí mật đáng tin; refresh, scope và thời điểm hết hạn được xử lý theo giao thức.

Đối với Bearer token, **`Authenticator` không phải nơi tự động xin/refresh OAuth2 access token**. `Bearer` và `Basic` là hai authentication scheme khác nhau. OAuth2/OpenID Connect còn liên quan cấp token, audience, scopes, refresh, expiration và có thể proof-of-possession; `PasswordAuthentication` không cung cấp các chức năng đó.

### Ví dụ Bearer header với nguồn cấu hình bảo vệ

```java
import java.net.URI;
import java.net.http.HttpRequest;

String token = System.getenv("SERVICE_ACCESS_TOKEN");
if (token == null || token.isBlank()) {
    throw new IllegalStateException(
            "Missing SERVICE_ACCESS_TOKEN");
}

HttpRequest bearerRequest = HttpRequest.newBuilder(
        URI.create("https://api.example.com/v1/private"))
        .header("Authorization", "Bearer " + token)
        .GET()
        .build();
```

Đây là **đoạn trong phương thức**, không gửi request tới URL giả. Environment variable là một **ví dụ nguồn cấu hình**; khi có secret manager hoặc workload identity được tổ chức phê duyệt, ưu tiên chúng. Không in `token` hoặc request headers vào log; kiểm soát thời hạn hiệu lực, audience, host và redirects.

## 8. Lấy thông tin context trong `getPasswordAuthentication()`

Một `Authenticator` có thể xử lý nhiều challenge khác nhau. Các phương thức sau hữu ích để quyết định **có trả credential hay không**:

| Method | Ý nghĩa thực hành | Ràng buộc |
| --- | --- | --- |
| `getRequestorType()` | `SERVER` hoặc `PROXY` | Không dùng cùng credential cho mọi type |
| `getRequestingHost()` | Host yêu cầu xác thực | Có thể `null`, dùng allowlist |
| `getRequestingPort()` | Port kết nối đang cần xác thực | Kiểm tra đúng service/proxy port |
| `getRequestingProtocol()` | Protocol yêu cầu kết nối, thường HTTP/HTTPS | Không nhầm với auth scheme |
| `getRequestingScheme()` | Authentication scheme, ví dụ `Basic` | Case-insensitive khi so sánh tên scheme |
| `getRequestingPrompt()` | Prompt/realm từ challenge | Kiểm tra realm nếu áp dụng |
| `getRequestingURL()` | URL liên quan đến yêu cầu xác thực | Có thể `null` theo context; không tự xem là origin đã được tin cậy |
| `getRequestingSite()` | `InetAddress` nếu có | Có thể `null`; đừng dựa độc quyền vào reverse DNS |

### Phân biệt "protocol" với "authentication scheme"

Giả sử truy cập `https://api.example.com/private` và server yêu cầu `Basic`:

- `getRequestingProtocol()` cho biết protocol của kết nối, thường `https`.
- `getRequestingScheme()` cho biết **HTTP authentication scheme**, ví dụ `basic`.
- `getRequestingPrompt()` có thể mang realm, ví dụ `"api"`.

Đừng viết:

```java
// SAI: Basic là authentication scheme, không phải URI scheme.
// "https".equalsIgnoreCase(getRequestingScheme())
```

Nếu ứng dụng cần bảo đảm transport là HTTPS, hãy xác thực **request URI/target policy** trước khi gửi, đồng thời kiểm tra context callback phù hợp. Việc thấy `Basic` không chứng minh TLS đang hoạt động.

### Trả `null` khi không đúng scope

Đây là lựa chọn an toàn:

```java
@Override
protected PasswordAuthentication getPasswordAuthentication() {
    if (getRequestorType() != RequestorType.SERVER
            || !"api.example.com".equalsIgnoreCase(
                    getRequestingHost())) {
        return null;
    }
    return new PasswordAuthentication(user, password.clone());
}
```

Đoạn này **chưa đủ** cho một hệ thống thực nếu chưa kiểm tra thêm port, scheme, realm, URL và redirect policy; nó minh họa nguyên tắc **không tự động cấp secret cho yêu cầu ngoài allowlist**. Khi một host có nhiều realm hoặc môi trường, việc scope theo mỗi host đơn thuần là quá rộng.

## 9. Cấu hình proxy và credential của proxy khác credential của server

Đối với ứng dụng doanh nghiệp đi qua proxy, dùng `HttpClient.Builder.proxy(ProxySelector)`. Ví dụ kết hợp authenticator theo proxy:

```java
import java.net.Authenticator;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.ProxySelector;
import java.net.http.HttpClient;

String proxyHost = "proxy.example.com";
int proxyPort = 8080;
String proxyUser = System.getenv("PROXY_USER");
String proxyPass = System.getenv("PROXY_PASSWORD");

if (proxyUser == null || proxyPass == null) {
    throw new IllegalStateException("Proxy credentials missing");
}

Authenticator proxyAuth = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        if (getRequestorType() == RequestorType.PROXY
                && proxyHost.equalsIgnoreCase(getRequestingHost())
                && getRequestingPort() == proxyPort
                && "basic".equalsIgnoreCase(
                        getRequestingScheme())) {
            return new PasswordAuthentication(
                    proxyUser, proxyPass.toCharArray());
        }
        return null;
    }
};

HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress(proxyHost, proxyPort)))
        .authenticator(proxyAuth)
        .build();
```

Đây là **mã minh họa**, chỉ hoạt động khi thực sự có proxy với authentication scheme tương thích; không có stdout cố định. Secret trong env chỉ là một phương án đơn giản để thể hiện nguồn cấu hình bên ngoài source.

**Những giới hạn cần nhớ:**

- `ProxySelector` quyết định proxy nào sử dụng; `Authenticator` quyết định credential khi challenge phù hợp.
- Khi gọi origin server, challenge từ server phải được phân biệt với challenge từ proxy.
- Trên HTTPS có proxy, giao thức CONNECT/tunnel và cấu hình JDK có thể hạn chế một số authentication scheme. Không vô hiệu hóa chính sách bảo vệ Basic qua tunnel một cách tùy tiện chỉ để "làm cho 407 biến mất".
- Nếu proxy yêu cầu Kerberos/Negotiate, NTLM hoặc scheme khác, đừng mặc định `HttpClient.Builder.authenticator` tích hợp hỗ trợ đủ. Cần kiểm tra support chính xác của JDK/deployment và chọn giải pháp phù hợp.
- Proxy là thành phần cơ sở hạ tầng có mức tin cậy riêng. Credential của proxy **không nên** được gửi qua `Authorization` cho origin server.

## 10. Authentication và SSL/TLS: bảo mật credential trên đường truyền

Bản thân Basic authentication **không mã hóa** user/password. Nó chỉ đặt `username:password` vào chuỗi Base64, có thể giải được.

Một cấu hình request Internet cần:

1. URI dùng `https://`, không thay bằng `http://` vì "đã có Basic auth".
2. TLS trust store/chứng chỉ được cấu hình đúng; không tắt hostname verification hoặc chấp nhận mọi certificate.
3. Không gửi credential cho hostname ngoài allowlist, kể cả sau redirect hoặc thay đổi DNS/proxy.
4. Chỉ cấp scope credential tối thiểu, rotate và revoke khi cần.
5. Không lưu secret trong URL như `https://user:pass@host` hoặc query parameters.
6. Không tự tin rằng mask một vài ký tự trong log đã loại bỏ rủi ro: HTTP headers, tracing, dumps và exception cũng cần kiểm soát.

**Không lẫn `Authenticator` với mutual TLS (mTLS).** mTLS dùng certificate/keypair tại tầng TLS, được cấu hình qua `SSLContext`/key manager theo thiết kế hệ thống. `Authenticator`/`PasswordAuthentication` xử lý HTTP credential challenge, không cung cấp client certificate. Một API có thể yêu cầu mTLS **và** HTTP Authorization cùng lúc.

### Redirect và nguy cơ gửi credential tới host ngoài ý muốn

`HttpClient` có chính sách follow redirects qua builder. Khi bật redirect, hãy đánh giá endpoint nào được phép nhận credential, đặc biệt khi chuyển host hoặc giảm mức bảo mật từ HTTPS sang HTTP.

Không chỉ dựa vào callback `getRequestingHost()` để chứng minh mọi request đích cuối cùng đều an toàn: ứng dụng vẫn phải kiểm tra URL đầu vào, URL sau redirects theo chính sách, proxy, và khả năng lộ credential khi sử dụng header `Authorization` đặt sẵn. Với token nhạy cảm, không tự động follow redirect sang origin không tin cậy.

### Credential rotation

Nếu credential thay đổi, một `Authenticator` chứa mật khẩu cố định có thể tiếp tục dùng bản cũ. Thiết kế production nên hỗ trợ lấy secret phiên bản hiện hành hoặc tái tạo client/authenticator theo vòng đời được kiểm soát. Không ghi credential vào singleton toàn cục theo cách khó rotate và khó kiểm soát môi trường.

## 11. Kiểm soát lỗi: callback không thay cho kiểm tra HTTP response

`Authenticator` chỉ giải quyết phần **cấp credential khi được yêu cầu**. Sau khi `send` hoàn thành, code vẫn cần kiểm tra:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

switch (response.statusCode()) {
    case 200:
        // Body hợp lệ theo contract API.
        break;
    case 401:
        // Credential thiếu/sai/hết hiệu lực hoặc challenge không xử lý được.
        break;
    case 403:
        // Quyền hoặc policy không cho phép.
        break;
    case 407:
        // Proxy yêu cầu xác thực.
        break;
    default:
        // Xử lý theo endpoint: 204, redirect, 429, 5xx...
}
```

Đây là **đoạn minh họa trong một phương thức** với `client` và `request` đã được khai báo; nội dung các nhánh phải theo business contract. Đặc biệt:

- Không coi mọi `2xx` đều có body văn bản. `204 No Content` có thể là thành công hợp lệ.
- Không retry mật khẩu vô hạn nếu liên tục nhận `401`; dễ gây lock tài khoản hoặc rate-limit.
- Không coi `403` là yêu cầu thay password mới. Kiểm tra scopes/roles/policy với người quản lý API.
- Một `IOException`, `HttpTimeoutException` hay lỗi TLS không đồng nghĩa password sai; phải xử lý transport riêng.
- Với `sendAsync`, lỗi transport/timeout có thể làm future hoàn thành exceptionally; còn một HTTP `401` có thể vẫn được biểu diễn bằng `HttpResponse` sau khi client xử lý challenge theo khả năng. Kiểm tra status ở stage xử lý kết quả.

### `sendAsync` với `Authenticator`

Cấu hình authenticator trên **HttpClient**, sau đó vẫn dùng async bình thường:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

CompletableFuture<String> body = future.thenApply(resp -> {
    if (resp.statusCode() != 200) {
        throw new IllegalStateException(
                "HTTP status " + resp.statusCode());
    }
    return resp.body();
});
```

Đây là **code minh họa** với các biến `client`, `request` và import `CompletableFuture` đã có. `Authenticator` có thể được hỏi trong quá trình xử lý async authentication; callback không nên làm network I/O nặng, in secret ra console hoặc phụ thuộc UI thread.

### Proxy/server challenge sai hoặc thiếu header

Response `401` mà thiếu hoặc có `WWW-Authenticate` không được client hỗ trợ có thể không kích hoạt callback phù hợp. Tương tự `407` mà proxy không gửi `Proxy-Authenticate` hợp lệ không đảm bảo được xử lý chỉ nhờ cấu hình authenticator.

Đừng giải quyết bằng cách tự động gắn Basic header lên **mọi request**. Hãy đối chiếu response status/challenge thực tế, cấu hình client, allowlist, scheme được hỗ trợ, proxy và TLS.

## 12. Quy trình thiết lập thực tế cho một HTTP API có Basic auth

Giả sử hệ thống đã có endpoint HTTPS và credential trong một nguồn bí mật được cấu hình an toàn.

**Bước 1 — Kiểm tra contract xác thực của API.** Endpoint dùng Basic, Bearer, mTLS hay ký yêu cầu? `Authenticator` hợp với challenge Basic được hỗ trợ; Bearer token nên dùng token provider và `Authorization` riêng.

**Bước 2 — Giới hạn origin và môi trường.** Không dùng một credential staging trên production; xác định host, port, realm, proxy và redirect policy. Đừng bỏ qua kiểm tra URL đến từ người dùng.

**Bước 3 — Triển khai `Authenticator` có allowlist.** Override `getPasswordAuthentication`, kiểm tra `RequestorType`, host/port, scheme, realm. Trả `null` khi challenge ngoài phạm vi; không đưa password ra log.

**Bước 4 — Đặt authenticator lên đúng `HttpClient`.**

```java
HttpClient client = HttpClient.newBuilder()
        .authenticator(authenticator)
        .build();
```

Có thể tái sử dụng `client` cho nhiều request **trong cùng trust boundary**. Không tạo một client dùng chung cho các tenant có credential khác nhau nếu không thiết kế cô lập và scope chặt.

**Bước 5 — Xây request HTTPS và gửi.**

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/private"))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
```

Đây là code trong phương thức có thể ném `IOException`/`InterruptedException`, và hostname chỉ là ví dụ. Không có stdout cố định.

**Bước 6 — Kiểm tra HTTP status, dữ liệu và lỗi.** Một `401`/`403` vẫn cần hướng xử lý hợp lý dù đã có client authenticator.

**Bước 7 — Giám sát an toàn.** Ghi status, endpoint định danh không chứa secret, thời gian phản hồi, số lỗi, loại challenge. Không log credential hoặc Base64 Basic token.

**Bước 8 — Kiểm thử và rotate.** Dùng fixture loopback như ở phần 6, thử credential sai, host sai, proxy challenge, header Authorization tự đặt, credential hết hạn/đổi và cách client phục hồi.

## 13. Authenticator so với các hình thức xác thực HTTP phổ biến

| Cơ chế | Credential | Khuyến nghị với Java 11 HttpClient |
| --- | --- | --- |
| HTTP Basic challenge | Username/password theo `WWW-Authenticate: Basic` | Dùng `Authenticator` có kiểm soát host/proxy và HTTPS |
| Proxy Basic | Username/password proxy theo `Proxy-Authenticate: Basic` | Dùng `ProxySelector` + `Authenticator` cho `RequestorType.PROXY` nếu JDK/deployment hỗ trợ |
| Bearer token | Access token trong `Authorization: Bearer ...` | Lấy/rotate token qua provider, đặt header chủ động; không giả định `Authenticator` tạo token |
| API key trong custom header | Key/secret do dịch vụ định nghĩa | Header theo API contract, secret manager, HTTPS |
| HMAC request signing | Chữ ký dựa trên method, path, body, timestamp... | Dùng SDK/signature implementation chính xác; không thay bằng Basic |
| OAuth2/OIDC | Access token, refresh, scopes/audience, identity flow | Dùng thư viện/SDK chuyên dụng để cấp và quản lý token; HTTP Client chỉ gửi request |
| mTLS | Client certificate/private key tại tầng TLS | Cấu hình SSL/TLS context; không phải `PasswordAuthentication` |

Không một lựa chọn nào tự giải quyết toàn bộ phân quyền hoặc secret lifecycle. Quan trọng là **khớp yêu cầu của server** và giữ bí mật credential qua hệ thống.

### Trường hợp server cần preemptive Basic

Một số API yêu cầu request đầu tiên đã có `Authorization: Basic ...`. Khi ấy ứng dụng có thể chủ động tạo header Basic **nếu chính sách và contract cho phép**:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String user = "demo";  // Chỉ minh họa; sản phẩm phải đọc từ secret manager.
String pass = "test";

String basic = Base64.getEncoder().encodeToString(
        (user + ":" + pass).getBytes(StandardCharsets.US_ASCII));

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/private"))
        .header("Authorization", "Basic " + basic)
        .GET()
        .build();
```

Đây không phải giải pháp mặc định khi đã cấu hình `Authenticator`: request đặt header sẵn dùng nhánh **explicit Authorization**; implementation JDK tích hợp không gọi callback để sửa credential khi server từ chối. Phải kiểm soát log/redirect và bảo vệ secret thật. Với username/password không thuần ASCII, không tự chọn `US_ASCII` mà cần contract encoding chính xác của server theo RFC 7617.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Có `Authenticator` nhưng server vẫn trả `401` | Challenge không hợp lệ/không hỗ trợ, password sai, host/realm scope không khớp | Xem status và `WWW-Authenticate` (không log secret), kiểm tra callback context và credential |
| `getPasswordAuthentication()` không được gọi | Không có challenge tương ứng, request đã có Authorization, scheme không hỗ trợ hoặc không đúng proxy/server | Kiểm tra flow thực, không giả định callback cho mọi request |
| HTTP `403` nhưng code cứ thay password | Authorization policy chặn, không phải challenge đăng nhập thông thường | Kiểm tra role/scope/quyền API thay vì retry mật khẩu |
| Credential server được gửi cho proxy | Không phân biệt `SERVER`/`PROXY` | Dùng `getRequestorType` và kho credential riêng |
| Cùng credential bị dùng cho mọi host | Callback luôn trả user/password | Allowlist host/port/realm/protocol, hạn chế redirects |
| Proxy trả `407` | Chưa cấu hình proxy auth hoặc proxy scheme bị chặn | `ProxySelector` + scoped proxy authenticator, kiểm tra tunnel và policy JDK |
| Server dùng Bearer nhưng callback trả password | Nhầm Basic challenge với token-based auth | Dùng token provider và `Authorization: Bearer` |
| Header Authorization tự đặt sai vẫn không được sửa | JDK dùng header explicit thay vì callback | Chọn **một** cơ chế cho từng request, sửa token/header tại nguồn |
| Authentication hoạt động trên HTTP nhưng lộ credential | Basic chỉ Base64, không encrypt | HTTPS/TLS, kiểm soát certificate và môi trường |
| Callback không có host hoặc URL | API có thể trả `null` ở một số context | Null-safe validation, trả `null` khi không đủ thông tin tin cậy |
| Lỗi TLS bị hiểu là sai mật khẩu | Chứng chỉ/hostname/trust store sai | Sửa TLS configuration, không vô hiệu hóa verification |
| Client retry đăng nhập mãi | Cơ chế retry thiếu giới hạn hoặc secret liên tục sai | Giới hạn retry, bảo vệ account lockout và audit |
| Token hết hạn nhưng dùng `PasswordAuthentication` | Lẫn giữa password callback và OAuth2 token lifecycle | SDK/token manager, refresh an toàn |
| Dùng `Authenticator.setDefault` gây ảnh hưởng ngoài ý muốn | Chính sách global thay đổi các kết nối khác | Gắn `Authenticator` trên `HttpClient.Builder` cụ thể |
| Log chứa `Authorization`/`Proxy-Authorization` | Ghi raw headers khi debug | Redaction/sanitization và phân quyền log |
| Thử với tài khoản thật trên HTTP loopback/fixture | Sao chép test setup sai phạm vi | Chỉ dùng credential giả trong fixture; production dùng HTTPS và secret manager |

## 15. Câu hỏi luyện tập có đáp án

**1.** `HttpClient.newBuilder().authenticator(auth).build()` có tự gửi password trong mọi request không?

**Đáp án:** Không nên hiểu như vậy. Authenticator cung cấp credential theo quá trình authentication của HTTP Client, thường khi nhận challenge phù hợp; implementation có thể có cache trạng thái. Không coi mỗi request đều gọi callback hay mọi kết nối đều gửi password ngay từ đầu.

**2.** Server trả `401` kèm `WWW-Authenticate: Basic realm="demo"`. Callback muốn cấp credential chỉ cho server đó thì cần kiểm tra gì?

**Đáp án:** Tối thiểu `RequestorType.SERVER`, host/port dự kiến, `getRequestingScheme()` là Basic và realm được chấp nhận; ngoài callback còn cần chính sách HTTPS/URL/redirect.

**3.** `getRequestingScheme()` trả `Basic` có chứng minh request đã dùng HTTPS không?

**Đáp án:** Không. `Basic` là HTTP **authentication scheme**; scheme của URI/transport là `http` hay `https`, thường xem ở request URI và thông tin protocol.

**4.** `PasswordAuthentication` lưu password dưới kiểu gì?

**Đáp án:** `char[]`. Việc dùng mảng ký tự cho phép kiểm soát một số bản sao, nhưng không tự bảo đảm loại bỏ hết dấu vết secret trong bộ nhớ.

**5.** Java client có authenticator rồi nhưng request đã gắn `Authorization: Bearer ...`. Với JDK HTTP Client tích hợp, callback có được gọi để sửa Bearer token sai không?

**Đáp án:** Không cho authentication tương ứng; explicit `Authorization` được ưu tiên và client không tự retry qua authenticator để chữa token. Cần token manager xử lý refresh/sửa token theo API.

**6.** `401` khác `407` thế nào?

**Đáp án:** `401` thường từ origin server với `WWW-Authenticate`/`Authorization`; `407` từ proxy với `Proxy-Authenticate`/`Proxy-Authorization`.

**7.** Server trả `403`. Có nên coi đó là tín hiệu gọi `getPasswordAuthentication` lần nữa không?

**Đáp án:** Không mặc định. `403` thường là vấn đề policy/authorization. Kiểm tra quyền và contract server.

**8.** Base64 trong HTTP Basic có mã hóa bảo mật mật khẩu không?

**Đáp án:** Không. Base64 có thể giải mã dễ dàng. Dùng HTTPS/TLS và quản lý secret đúng quy trình.

**9.** Có thể dùng `Authenticator` để tự động cấp OAuth2 access token hoặc refresh token không?

**Đáp án:** Không phải chức năng chuẩn của nó. Dùng SDK/token provider và gắn `Authorization: Bearer` khi thích hợp.

**10.** Callback `getRequestingHost()` có thể `null` không?

**Đáp án:** Có theo hợp đồng API. Cần kiểm tra null và từ chối cấp credential nếu không xác minh được đích.

**11.** Với hai service và hai bộ credential khác nhau, có nên dùng một authenticator luôn trả cùng password không?

**Đáp án:** Không. Phải phân quyền theo service, host/port, realm và trust boundary; thường nên dùng các client cấu hình riêng hoặc một bộ chọn secret được kiểm soát chặt.

**12.** Chương trình loopback trả `withoutAuth=401` và `withAuth=200` chứng minh điều gì?

**Đáp án:** Cùng một endpoint Basic yêu cầu credential; client có scoped `Authenticator` đáp ứng challenge trong kịch bản thử nghiệm. Nó không chứng minh gửi Basic qua HTTP Internet là an toàn.

**13.** `HttpClient.sendAsync` có dùng authenticator cấu hình trên client không?

**Đáp án:** Có trong phạm vi hỗ trợ của client; async chỉ thay cách trả kết quả bằng `CompletableFuture`. Vẫn phải kiểm tra lỗi và HTTP status.

**14.** Khi client gặp `HttpTimeoutException`, có phải password sai?

**Đáp án:** Không. Đó là vấn đề timeout/transport; xử lý độc lập với authentication status.

## Tài liệu chuẩn còn áp dụng

- [Oracle Java SE 11 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `authenticator(Authenticator)`, proxy, timeout và các thiết lập của HTTP client.
- [Oracle Java SE 26 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): implementation note về `Authorization`/`Proxy-Authorization` tự đặt và hỗ trợ HTTP Basic của JDK client tích hợp.
- [Oracle Java SE 11 — `Authenticator`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/Authenticator.html): `getPasswordAuthentication`, `RequestorType`, requesting host/port/scheme/prompt/protocol/URL.
- [Oracle Java SE 11 — `PasswordAuthentication`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/PasswordAuthentication.html): cặp username/password.
- [Oracle Java SE 11 — `HttpClient`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client cấu hình qua builder, `send` và `sendAsync`.
- [Oracle Java SE 11 — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): xây request và đặt header có chủ đích.
- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617.html): Basic, realm, Base64, charset và các lưu ý bảo mật.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): status `401`, `403`, `407`, `WWW-Authenticate` và `Proxy-Authenticate`.

**Điểm cần nhớ:** `Authenticator` là **nguồn credential theo challenge** được gắn vào `HttpClient`, không phải công cụ phân quyền hay OAuth client. Với Basic, cần giới hạn đúng server/proxy, host/port/realm, ưu tiên HTTPS và không làm lộ secret. Khi request tự có `Authorization`, caller phải chủ động quản lý credential đó; luôn kiểm tra response status dù quá trình xác thực đã chạy.