# Java 11+ — HTTP Client: Khởi tạo client bằng Builder

## 1. `HttpClient.newBuilder()` giải quyết vấn đề gì?

Từ **Java 11**, module `java.net.http` cung cấp API chuẩn để gửi yêu cầu HTTP đồng bộ (`send`) hoặc bất đồng bộ (`sendAsync`). Trọng tâm của bài này là **khởi tạo và cấu hình `HttpClient` bằng Builder**, trước khi tạo các `HttpRequest`.

Cấu trúc phổ biến:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .version(HttpClient.Version.HTTP_2)
        .build();
```

Cần import `java.net.http.HttpClient` và `java.time.Duration`. Quy trình gồm ba bước:

1. Gọi **`HttpClient.newBuilder()`** để lấy `HttpClient.Builder`.
2. Gọi các phương thức cấu hình mong muốn; mỗi phương thức trả về **chính builder đó** để gọi nối tiếp (*fluent API*).
3. Gọi **`build()`** để tạo một đối tượng `HttpClient` mới với cấu hình đã chọn.

Sau `build()`, `HttpClient` có cấu hình **bất biến** (immutable) và thường được **tái sử dụng** cho nhiều request, giúp chia sẻ quản lý kết nối và các tài nguyên liên quan. Không cần tạo một client mới cho mọi request. Ngược lại, **`HttpClient.Builder` có trạng thái thay đổi được và không thread-safe**: không dùng cùng một builder để cấu hình đồng thời từ nhiều luồng nếu không tự đồng bộ.

## 2. Khi nào cần Builder, khi nào dùng mặc định?

Nếu hoàn toàn chấp nhận thiết lập mặc định:

```java
HttpClient defaultClient = HttpClient.newHttpClient();
```

Theo hợp đồng API, lệnh trên tương đương **`HttpClient.newBuilder().build()`**.

Dùng Builder khi ứng dụng cần **chính sách chung cho một client**: thời gian chờ **thiết lập kết nối**, chuyển hướng, phiên bản HTTP ưu tiên, proxy, cookie, xác thực, TLS hoặc executor. Ví dụ:

```java
HttpClient apiClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(8))
        .followRedirects(HttpClient.Redirect.NEVER)
        .proxy(HttpClient.Builder.NO_PROXY)
        .build();
```

Ở đây `NO_PROXY` yêu cầu kết nối trực tiếp, hữu ích khi nghiệp vụ **cố ý** không cho đi qua proxy. Nếu không gọi `proxy(...)`, client có thể sử dụng **proxy selector mặc định của môi trường**, nên “không cấu hình proxy” **không đồng nghĩa** “chắc chắn không đi qua proxy”.

**Lưu ý tên dễ nhầm:** `HttpClient.newBuilder()` xây client. `HttpRequest.newBuilder()` xây **một request**; hai builder có vai trò khác nhau.

## 3. Các tùy chọn cấu hình quan trọng của `HttpClient.Builder`

| Phương thức | Tác dụng | Khi nào cần |
| --- | --- | --- |
| `connectTimeout(Duration)` | Giới hạn thời gian **thiết lập kết nối mới**. | Muốn không chờ kết nối mạng quá lâu. |
| `followRedirects(HttpClient.Redirect)` | Quy định có tự theo HTTP redirect không. | Cần kiểm soát chính sách chuyển hướng. |
| `version(HttpClient.Version)` | Chọn phiên bản giao thức HTTP **ưu tiên**; không phải cam kết phiên bản cuối cùng. | Có yêu cầu tương thích HTTP/1.1 hoặc ưu tiên HTTP/2. |
| `proxy(ProxySelector)` | Cấu hình cách chọn proxy; có hằng `NO_PROXY`. | Hạ tầng có proxy, hoặc ứng dụng buộc kết nối trực tiếp. |
| `authenticator(Authenticator)` | Cấp cơ chế xác thực theo challenge HTTP khi phù hợp. | Dùng xác thực phía HTTP/proxy theo yêu cầu hệ thống. |
| `cookieHandler(CookieHandler)` | Đọc/ghi cookie thông qua handler được chọn. | Cần quản lý phiên/cookie, hoặc muốn chính sách từ chối cookie rõ ràng. |
| `sslContext(SSLContext)` | Chọn TLS context, trust/key material theo cấu hình ứng dụng. | mTLS, CA doanh nghiệp hoặc cấu hình TLS riêng có căn cứ. |
| `sslParameters(SSLParameters)` | Chọn những tùy chọn TLS được hỗ trợ. | Cần tinh chỉnh TLS theo chính sách bảo mật. |
| `executor(Executor)` | Chỉ định executor cho tác vụ bất đồng bộ/phụ thuộc. | Cần chính sách quản lý tài nguyên/luồng riêng. |
| `priority(int)` | Thiết lập mức ưu tiên mặc định cho HTTP/2 từ **1 đến 256**. | Chỉ với trường hợp có yêu cầu HTTP/2 cụ thể. |
| `build()` | Tạo **client mới** từ trạng thái builder. | Kết thúc bước cấu hình. |

Đây là các cấu hình cốt lõi có mặt từ Java 11 và vẫn được hỗ trợ trong Java hiện đại. Các JDK mới có thể bổ sung tùy chọn Builder khác, nhưng ví dụ chính của bài chỉ sử dụng API tương thích Java 11.

### 3.1. `connectTimeout` không phải timeout của toàn bộ request

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();
```

Giới hạn 5 giây chỉ áp dụng trong trường hợp client **cần thiết lập một kết nối mới**. Nếu đã tái sử dụng kết nối trước đó, giới hạn này có thể không phát huy tác dụng. Nếu thiết lập kết nối quá hạn, `send` có thể ném `HttpConnectTimeoutException` và `sendAsync` có thể hoàn tất exceptionally với ngoại lệ đó.

Giá trị `Duration` phải **lớn hơn 0**; `Duration.ZERO` hoặc giá trị âm sẽ gây `IllegalArgumentException` tại lúc cấu hình. Đừng dùng `connectTimeout` để tuyên bố thời hạn tổng của tất cả các bước gửi request/nhận response.

Muốn đặt thêm timeout ở **mức request**, hãy cấu hình `HttpRequest.Builder.timeout(Duration)`:

```java
// Đoạn minh họa; URI là endpoint ứng dụng muốn gọi.
// Không phát sinh kết nối chỉ bằng việc tạo request.
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/"))
        .timeout(Duration.ofSeconds(15))
        .GET()
        .build();
```

Đoạn trên cần import `java.net.URI`, `java.net.http.HttpRequest` và `java.time.Duration`. Timeout request và timeout kết nối giải quyết **hai phạm vi khác nhau**. Chính sách retry, tổng hạn mức của chuỗi retry, DNS và chờ xử lý ở tầng ứng dụng vẫn cần được cân nhắc riêng.

### 3.2. `followRedirects`: chính sách chuyển hướng

Có ba giá trị thường dùng:

- **`NEVER`:** không tự đi theo redirect; đây là mặc định trong Java 11.
- **`NORMAL`:** đi theo redirect phù hợp nhưng **không tự chuyển từ HTTPS xuống HTTP**.
- **`ALWAYS`:** cho phép đi theo redirect kể cả khi chuyển từ HTTPS sang HTTP, vì vậy cần cân nhắc kỹ rủi ro bảo mật.

`followRedirects` không có nghĩa tự động coi mọi HTTP 3xx là thành công. Khi chính sách không cho theo redirect, ứng dụng sẽ nhận response để tự xử lý. Nếu máy chủ chuyển đến domain khác, cần xem xét rò rỉ credential/header/cookie, chính sách xác thực và yêu cầu nghiệp vụ; không đơn giản bật `ALWAYS` chỉ để “cho khỏi lỗi”.

### 3.3. `version` là ưu tiên, không phải cam kết

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

Trong Java 11, các lựa chọn là `HTTP_1_1` và `HTTP_2`; mặc định client **ưu tiên HTTP/2**. Tuy nhiên, server, TLS, proxy và khả năng của implementation có thể khiến kết nối thực tế dùng HTTP/1.1 dù ưu tiên HTTP/2.

Phân biệt:

- `client.version()` phản ánh **phiên bản ưu tiên cấu hình**.
- `response.version()` phản ánh **phiên bản giao thức của response cụ thể**.

Không dùng `client.version() == HTTP_2` làm bằng chứng mọi response đều qua HTTP/2. Các Java hiện đại có thể bổ sung hỗ trợ giao thức mới, nhưng ứng dụng biên dịch với `--release 11` chỉ nên dùng tập API phiên bản Java 11.

## 4. Cấu hình mặc định: đọc đúng ý nghĩa getter

Trong Java 11, các giá trị quan trọng khi **không** gọi setter trên builder:

| Thuộc tính | Mặc định/ý nghĩa |
| --- | --- |
| Chuyển hướng | `HttpClient.Redirect.NEVER`. |
| Phiên bản HTTP ưu tiên | `HttpClient.Version.HTTP_2`. |
| `connectTimeout()` | `Optional.empty()` khi không đặt thời hạn tường minh. **Không** có nghĩa kết nối thực tế sẽ chắc chắn chờ vô hạn. |
| `proxy()` | Có thể là `Optional.empty()` khi không cấu hình **proxy selector tường minh**. Client vẫn có thể dùng selector mặc định của hệ thống. |
| `executor()` | `Optional.empty()` khi không cung cấp executor. Implementation vẫn có executor nội bộ cho tác vụ cần thiết. |
| `cookieHandler()` | `Optional.empty()` nếu không cấu hình cookie handler. |
| `sslContext()` | Context TLS mặc định khi không đưa context riêng. |

**Lỗi logic thường gặp:** `client.proxy().isEmpty()` **không chứng minh** yêu cầu đi thẳng ra Internet; nó chỉ chứng minh client không có `ProxySelector` **được cấu hình tường minh trên Builder**. Nếu yêu cầu bảo đảm không proxy, dùng `proxy(HttpClient.Builder.NO_PROXY)`.

Tương tự, `client.executor().isEmpty()` không có nghĩa client thực hiện mọi thao tác bất đồng bộ trên luồng hiện tại.

## 5. Ví dụ Java 11+ hoàn chỉnh và kết quả đã kiểm chứng

Ví dụ sau **không gửi request ra mạng**. Nó chỉ xây các HTTP client và kiểm tra cấu hình có thể đọc lại, vì vậy chạy được không cần Internet hoặc máy chủ.

Lưu thành tệp **`HttpClientBuilderDemo.java`**:

```java
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.http.HttpClient;
import java.time.Duration;

public final class HttpClientBuilderDemo {
    public static void main(String[] args) {
        HttpClient.Builder builder = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .version(HttpClient.Version.HTTP_2)
                .proxy(HttpClient.Builder.NO_PROXY)
                .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_NONE));

        HttpClient configured = builder.build();
        System.out.println("configured-timeout-seconds="
                + configured.connectTimeout().orElseThrow().getSeconds());
        System.out.println("configured-redirect=" + configured.followRedirects());
        System.out.println("configured-version=" + configured.version());
        System.out.println("configured-proxy-present=" + configured.proxy().isPresent());
        System.out.println("configured-cookie-handler=" + configured.cookieHandler().isPresent());

        HttpClient defaults = HttpClient.newHttpClient();
        System.out.println("default-redirect=" + defaults.followRedirects());
        System.out.println("default-version=" + defaults.version());
        System.out.println("default-timeout-present=" + defaults.connectTimeout().isPresent());

        builder.followRedirects(HttpClient.Redirect.NEVER);
        HttpClient another = builder.build();
        System.out.println("original-redirect=" + configured.followRedirects());
        System.out.println("another-redirect=" + another.followRedirects());

        try {
            HttpClient.newBuilder().connectTimeout(Duration.ZERO);
            System.out.println("zero-timeout=unexpected-success");
        } catch (IllegalArgumentException expected) {
            System.out.println("zero-timeout=IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy với **JDK 11 trở lên**; cờ `--release 11` xác minh chương trình chỉ dùng API tương thích Java 11:

```bash
javac -encoding UTF-8 --release 11 HttpClientBuilderDemo.java
java HttpClientBuilderDemo
```

Kết quả stdout:

```text
configured-timeout-seconds=5
configured-redirect=NORMAL
configured-version=HTTP_2
configured-proxy-present=true
configured-cookie-handler=true
default-redirect=NEVER
default-version=HTTP_2
default-timeout-present=false
original-redirect=NORMAL
another-redirect=NEVER
zero-timeout=IllegalArgumentException
```

Giải thích:

1. **`configured-timeout-seconds=5`:** thời hạn kết nối được lưu trong client và đọc lại qua `Optional<Duration>`.
2. **`configured-redirect=NORMAL`:** client thứ nhất có chính sách redirect do ứng dụng đặt, không phải mặc định `NEVER`.
3. **`configured-version=HTTP_2`:** đây là phiên bản **ưu tiên**; chương trình không thực hiện HTTP handshake nên không chứng minh server nào hỗ trợ HTTP/2.
4. **`configured-proxy-present=true`:** do đã chỉ định `NO_PROXY` tường minh; `Optional` có giá trị dù chính sách là **không dùng proxy**.
5. **`configured-cookie-handler=true`:** đã gắn `CookieManager`. Chính sách `CookiePolicy.ACCEPT_NONE` chọn **không chấp nhận cookie**, khác với “không có handler”.
6. **`default-redirect=NEVER`, `default-version=HTTP_2`, `default-timeout-present=false`:** phản ánh các mặc định của client được tạo bằng `newHttpClient()`.
7. **`original-redirect=NORMAL` và `another-redirect=NEVER`:** thay đổi builder **sau lần `build()` đầu** không làm thay đổi cấu hình của client đã tạo. Lần `build()` tiếp tạo client mới.
8. **`zero-timeout=IllegalArgumentException`:** thời hạn kết nối `Duration.ZERO` bị từ chối ngay ở bước cấu hình.

**Tính độc lập sau `build()` không có nghĩa builder trở thành bất biến.** Có thể dùng builder để tạo thêm client, nhưng mỗi lần `build()` tạo đối tượng client mới và có thể có tài nguyên riêng. Trong ứng dụng thông thường, nên xây client tại ranh giới cấu hình, rồi tái sử dụng client đó.

## 6. Phân tách `HttpClient.Builder` với `HttpRequest.Builder`

Một client có thể thực hiện **nhiều request khác nhau** mà không cần xây client mới:

```java
// Đoạn minh họa cho ứng dụng đã có HttpClient client.
// Cần import URI, HttpRequest, HttpResponse, Duration và IOException.
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/"))
        .timeout(Duration.ofSeconds(15))
        .header("Accept", "application/json")
        .GET()
        .build();

// Lệnh dưới thực sự gọi mạng; KHÔNG thuộc ví dụ chạy offline ở mục 5.
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.statusCode());
```

`client.send(...)` là lệnh đồng bộ và có thể ném `IOException` hoặc `InterruptedException`; ví dụ cần nằm trong phương thức có `throws` phù hợp hoặc khối `try/catch`. `sendAsync(...)` trả `CompletableFuture<HttpResponse<T>>` và cần xử lý completion/error theo luồng bất đồng bộ.

| Đặt ở đâu | Ví dụ thiết lập | Phạm vi |
| --- | --- | --- |
| **`HttpClient.Builder`** | `connectTimeout`, `followRedirects`, `version`, `proxy`, `sslContext`, `executor`. | Chính sách chung của nhiều request cùng một client. |
| **`HttpRequest.Builder`** | `uri`, `timeout`, `header`, `GET`, `POST`, request body. | Thuộc tính của một request cụ thể. |

Không đặt `connectTimeout` trên `HttpRequest.Builder` vì đó là API **của client**. Ngược lại, `HttpClient.Builder` không có phương thức `GET()` hoặc `uri(...)` để chỉ định endpoint gửi request.

## 7. Proxy, xác thực và cookie: thiết lập đúng phạm vi

### Proxy

```java
// Dùng proxy HTTP cụ thể khi hạ tầng cho phép:
ProxySelector fixedProxy =
        ProxySelector.of(new InetSocketAddress("proxy.example.com", 8080));

HttpClient throughProxy = HttpClient.newBuilder()
        .proxy(fixedProxy)
        .build();
```

Đoạn này chỉ minh họa cách cấu hình, không kết nối thật; cần import `java.net.ProxySelector`, `java.net.InetSocketAddress` và `java.net.http.HttpClient`. Đừng đưa một proxy bất kỳ vào production nếu không thuộc hạ tầng thật. Nếu muốn nhận cấu hình proxy hệ thống, cân nhắc giữ mặc định thay vì chỉ định hằng `NO_PROXY`.

### Authenticator

```java
HttpClient client = HttpClient.newBuilder()
        .authenticator(myAuthenticator) // một java.net.Authenticator được ứng dụng cấp
        .build();
```

Đây là đoạn minh họa cần có biến `myAuthenticator` hợp lệ. `Authenticator` hỗ trợ cơ chế xác thực phù hợp với `HttpClient`/proxy của implementation. Nó không phải nơi đặt **Bearer token** cho mọi API; khi server yêu cầu Authorization header theo hợp đồng riêng, thiết lập chính sách phù hợp trên request và bảo vệ bí mật bằng cơ chế quản lý credential của ứng dụng. Không hard-code password/token vào bài kiểm thử hoặc nguồn production.

### Cookie

```java
CookieManager cookies = new CookieManager();
cookies.setCookiePolicy(CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookies)
        .build();
```

Đoạn trên cần import `java.net.CookieManager`, `java.net.CookiePolicy`. Việc gắn `CookieManager` khiến client quản lý cookie theo chính sách được chọn. Nếu không cần lưu phiên/cookie, không nên tự động tạo kho cookie chung cho những hệ thống không tin cậy. Nếu ứng dụng cần tách phiên giữa nhiều tenant/tài khoản, **đừng chia sẻ** một handler chứa cookie giữa các ngữ cảnh mà dữ liệu phải cách ly.

## 8. TLS/HTTPS: giữ xác thực an toàn

Builder có thể nhận:

```java
HttpClient client = HttpClient.newBuilder()
        .sslContext(configuredSslContext)
        .sslParameters(configuredSslParameters)
        .build();
```

Đoạn minh họa cần `configuredSslContext` là `javax.net.ssl.SSLContext` đã cấu hình và `configuredSslParameters` là `javax.net.ssl.SSLParameters`. Phần lớn ứng dụng có thể dùng **SSLContext mặc định** mà không cần gọi hai setter trên. Chỉ cấu hình riêng khi có lý do thực tế như mutual TLS (mTLS), kho CA tổ chức hoặc chính sách giao thức được quản lý.

**Không** tạo một trust manager “tin tất cả certificate” hay tắt xác thực hostname chỉ để request chạy qua lỗi TLS. Cần xử lý certificate chain, hostname và truststore đúng cách. Một số `SSLParameters` có thể do implementation HTTP client kiểm soát hoặc bị bỏ qua; không giả định mọi tùy chọn TLS đều được áp dụng nguyên trạng.

Với `followRedirects(HttpClient.Redirect.ALWAYS)`, cũng cần xem xét chính sách HTTPS và việc theo đường dẫn chuyển hướng đến origin khác. Builder không thay thế quy tắc bảo vệ thông tin xác thực.

## 9. Executor, đồng thời và vòng đời tài nguyên

`executor(Executor)` hữu ích khi hệ thống cần kiểm soát riêng tài nguyên phục vụ công việc bất đồng bộ:

```java
// Đoạn minh họa trong ứng dụng quản lý executor ở cấp vòng đời.
ExecutorService pool = Executors.newFixedThreadPool(4);
HttpClient client = HttpClient.newBuilder()
        .executor(pool)
        .build();

// Ứng dụng sử dụng client...
// Khi không còn request/tác vụ dùng executor, shutdown pool theo vòng đời ứng dụng.
pool.shutdown();
```

Cần import `java.util.concurrent.ExecutorService` và `java.util.concurrent.Executors`. Không gọi `pool.shutdown()` ngay khi vẫn còn request bất đồng bộ đang chạy: điều đó có thể làm gián đoạn khả năng thực thi tác vụ tiếp theo. Khi cần bảo đảm kết thúc, theo dõi các `CompletableFuture` và điều phối shutdown ở ranh giới lifecycle. Phần lớn trường hợp không cần tự đặt executor; có thể dùng executor mặc định do implementation quản lý.

**Tái sử dụng `HttpClient`:** client đã `build()` có thể gửi nhiều request, thường có pool kết nối và tài nguyên dùng chung, do đó tạo một client trên mỗi request có thể gây tốn tài nguyên và mất lợi thế tái sử dụng. Có thể cung cấp client qua dependency injection/configuration ở cấp service.

**Khác biệt giữa Java 11 và phiên bản mới:** trong Java 11, `HttpClient` **không implements `AutoCloseable`**, vì vậy không viết `try (HttpClient client = ...)` trong ví dụ biên dịch `--release 11`. Từ **Java 21**, API bổ sung `close()` và các thao tác quản lý vòng đời client; trên JDK mới có thể dùng chúng khi quản lý tài nguyên. Kiến thức về Builder, client bất biến và tái sử dụng vẫn áp dụng; phần lifecycle phải dựa vào **JDK đích**. Trong mọi phiên bản, với HTTP response dạng stream, người gọi cần đọc/hủy/đóng tài nguyên response tương ứng theo hợp đồng body handler.

## 10. Những lỗi thường gặp khi khởi tạo Client

| Sai lầm | Cách sửa |
| --- | --- |
| “`newBuilder()` trả ngay một `HttpClient` đã sẵn sàng gửi request.” | Nó trả `HttpClient.Builder`; phải gọi **`build()`**. |
| “Chỉnh sửa builder sau `build()` cũng đổi client đã tạo.” | Không; mỗi client đã build có cấu hình bất biến. |
| “Builder có thể dùng đồng thời trên nhiều thread.” | Builder không thread-safe; cấu hình trước khi công bố client. |
| “`connectTimeout` giới hạn toàn bộ thời gian request.” | Nó giới hạn **mở kết nối mới**; dùng thêm `HttpRequest.timeout(...)` khi cần. |
| “`connectTimeout(Duration.ZERO)` nghĩa là không đặt timeout.” | Không hợp lệ: ném `IllegalArgumentException`. Nếu muốn không đặt, đừng gọi setter. |
| “`HTTP_2` bảo đảm response HTTP/2.” | Chỉ là lựa chọn ưu tiên; kiểm tra `response.version()` của request thực. |
| “Không gọi `proxy(...)` tức là không có proxy.” | Có thể vẫn dùng proxy selector mặc định; dùng `NO_PROXY` khi yêu cầu kết nối trực tiếp. |
| “`proxy().isEmpty()` chứng minh request đi trực tiếp.” | Chỉ nói client không có proxy selector được cấu hình tường minh. |
| “`executor().isEmpty()` tức client không có executor.” | Implementation có thể dùng executor nội bộ. |
| “`followRedirects(ALWAYS)` luôn là lựa chọn an toàn.” | Có thể theo redirect nhạy cảm, bao gồm HTTPS xuống HTTP; chọn chính sách phù hợp. |
| “Mỗi request cần một client mới.” | Thường nên tạo ít client và tái sử dụng với cùng cấu hình, để hưởng lợi pool kết nối. |
| “Trong Java 11, `HttpClient` dùng trực tiếp try-with-resources.” | Không tương thích Java 11; API quản lý `close()` được bổ sung từ Java 21. |
| “Dùng `sslContext` tự tạo trust-all giúp kết nối an toàn.” | Việc bỏ kiểm tra chứng chỉ làm giảm bảo mật; dùng truststore/CA đúng chính sách. |
| “Cấu hình client là đủ, không cần kiểm tra response.” | Vẫn phải xử lý status code, dữ liệu phản hồi, lỗi và timeout request phù hợp. |

## 11. Checklist thực hành

1. Xác định ứng dụng cần **cấu hình chung nào**: connect timeout, redirect, phiên bản ưu tiên, proxy, cookie, auth, TLS hay executor. Nếu không cần gì đặc biệt, `HttpClient.newHttpClient()` là đủ.
2. Tạo `HttpClient.Builder` bằng `HttpClient.newBuilder()`, gọi các setter **trước** khi `build()`.
3. Đặt thời hạn kết nối **dương**, đồng thời xem xét timeout cho **từng request** theo yêu cầu hệ thống.
4. Không giả định ưu tiên HTTP/2 đồng nghĩa thực tế HTTP/2; không giả định proxy Optional rỗng đồng nghĩa đi trực tiếp.
5. Chọn redirect có cân nhắc bảo mật; không mặc định cho phép HTTPS chuyển sang HTTP.
6. Giữ TLS validation đúng; bảo vệ token, password và cookie, tách trạng thái người dùng/tenant theo chính sách.
7. Xây client một lần hoặc một số ít lần theo **profile cấu hình**, sau đó tái sử dụng cho nhiều request; không chia sẻ builder chưa build giữa các luồng.
8. Chỉ tự đặt executor khi cần và quản lý vòng đời pool sau khi các tác vụ liên quan kết thúc.
9. Phân biệt code **biên dịch Java 11** với API được thêm vào JDK mới: không đưa `HttpClient.close()` vào ví dụ `--release 11`.
10. Kiểm thử bằng getter của client để khẳng định cấu hình, và kiểm thử request thực tế riêng để khẳng định redirect, proxy, HTTP version thương lượng, TLS và hành vi mạng.

### Tài liệu chính thức

- [Java SE 11 — `HttpClient`: `newBuilder()`, `newHttpClient()`, cấu hình mặc định](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 11 — `HttpClient.Builder`: đầy đủ setter và `build()`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 11 — `HttpRequest.Builder`: cấu hình mức request](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 26 — `HttpClient`: API hiện đại và quản lý vòng đời (các API sau Java 11)](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
