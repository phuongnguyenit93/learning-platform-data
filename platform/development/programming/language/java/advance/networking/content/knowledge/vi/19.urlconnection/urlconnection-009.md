# So sánh API cũ với HttpClient khi đọc hoặc chuyển đổi mã hiện có

**Chủ đề:** Java Advance - networking  
**Nhóm:** URLConnection  
**Môi trường:** Java 17+, đặc biệt là chuyển đổi từ **java.net.URLConnection / HttpURLConnection / HttpsURLConnection** sang **java.net.http.HttpClient** (có từ Java 11).

Trong các hệ thống Java lâu năm, một HTTP call thường bắt đầu bằng **new URL(...).openConnection()**, tiếp tục với **setRequestMethod()**, **setRequestProperty()**, **getInputStream()**, **getErrorStream()** và kết thúc bằng **disconnect()**. Java 11 bổ sung **HttpClient** hiện đại với **HttpRequest**, **HttpResponse**, **BodyHandler/BodyPublisher**, hỗ trợ gửi đồng bộ, bất đồng bộ và HTTP/2. Chuyển từ API cũ sang API mới **không chỉ là đổi tên method**: status/error body, redirect, timeout, cookie, proxy, charset, TLS, streaming và quản lý resource có thể khác nhau.

Bài học này giải thích cách đọc đúng đoạn mã legacy, kiểm tra ngữ nghĩa trước khi chuyển, lập bảng tương đương API, xử lý các trường hợp khó, và cung cấp một chương trình **Java 17 độc lập đã biên dịch/chạy** dùng **cả hai API** trên cùng một server HTTP loopback. Mục tiêu là **giữ hành vi ứng dụng** trước khi tối ưu hóa theo khả năng mới.

## 1. Mô hình cũ và mới

### URLConnection / HttpURLConnection: một đối tượng có trạng thái

~~~text
URL (resource identifier)
  |
  +-- openConnection()
          |
          +-- URLConnection (generic)
          |      setConnectTimeout, setReadTimeout,
          |      setRequestProperty, getInputStream...
          |
          +-- HttpURLConnection (HTTP-specific)
                 setRequestMethod, getResponseCode,
                 getErrorStream, setInstanceFollowRedirects,
                 disconnect...
~~~

**URL** là representation của một địa chỉ, còn **URLConnection** là liên kết truy cập một resource qua URL. **HttpURLConnection** kế thừa URLConnection và bổ sung semantics HTTP. **HttpsURLConnection** tiếp tục kế thừa HttpURLConnection, thêm các tùy chọn TLS.

Lộ trình thường gặp:

1. **openConnection()** trả một connection object nhưng không nhất thiết mở TCP ngay.
2. Gọi các setter **trước khi kết nối**: method, headers, timeouts, redirect, doOutput, streaming mode.
3. Gọi **connect()**, **getOutputStream()**, **getResponseCode()** hoặc **getInputStream()** để kích hoạt network I/O khi cần.
4. Lấy **HTTP status** qua **getResponseCode()**; đọc success body qua **getInputStream()** hoặc error body qua **getErrorStream()**.
5. Đóng InputStream/OutputStream bằng try-with-resources và gọi **disconnect()** trong finally khi không dùng nữa.

**Không ép mọi URLConnection thành HttpURLConnection:**

~~~java
URLConnection connection = new URL(someUrl).openConnection();
HttpURLConnection http = (HttpURLConnection) connection;
~~~

Đây chỉ là snippet khi **someUrl** dùng handler HTTP/HTTPS thích hợp. Với **file:**, **jar:** và những URL protocols khác, cast có thể gây **ClassCastException**. Trong migration, giữ những URLConnection dùng cho non-HTTP resource thay vì chuyển máy móc sang HttpClient.

### HttpClient: tách chính sách client, request và response

~~~text
HttpClient.Builder
    -> build() -> HttpClient [immutable configuration]
                       |
                       +--> HttpRequest.Builder
                       |         -> build() -> HttpRequest
                       |
                       +--> send(request, BodyHandler)
                       |       -> HttpResponse<T>
                       |
                       +--> sendAsync(request, BodyHandler)
                               -> CompletableFuture<HttpResponse<T>>
~~~

**HttpClient** sau khi build là đối tượng cấu hình có thể **tái sử dụng giữa nhiều requests**. **HttpRequest** chứa URI, method, headers, body publisher và request timeout. **HttpResponse<T>** có status, headers, body, URI, phiên bản HTTP và các thông tin response khác.

**Khác biệt dễ gây lỗi:** HttpClient **không tự ném IOException chỉ vì status 404 hoặc 500**. Khi có HTTP response hoàn chỉnh theo BodyHandler, **response.statusCode()** vẫn là 404/500 và **response.body()** có thể chứa error body. Legacy getInputStream() có thể ném IOException trên 4xx/5xx, nên nhiều hệ thống cũ cần **getErrorStream()**.

## 2. Bảng đối chiếu API khi review mã

| Mục đích | Legacy URLConnection / HttpURLConnection | HttpClient Java 17 | Điều cần xác minh |
| --- | --- | --- | --- |
| Resource URI | **new URL(text)** | **URI.create(text)** | URL và URI có khác biệt về parsing/encoding |
| Mở handle | **url.openConnection()** | **HttpRequest.newBuilder(uri)** | Builder chưa gửi network I/O |
| GET | **setRequestMethod("GET")** | **.GET()** | Method và query giữ nguyên |
| POST | **setRequestMethod("POST"); setDoOutput(true)** | **.POST(BodyPublishers.ofString(...))** | Content-Type, charset, body bytes |
| PUT | **setRequestMethod("PUT")** | **.PUT(BodyPublisher)** | Side effects và idempotency |
| DELETE | **setRequestMethod("DELETE")** | **.DELETE()** | Status/body contract |
| Custom method | **setRequestMethod(...)** (có giới hạn implementation) | **.method(name,publisher)** | PATCH/custom verb, server behavior |
| Request header | **setRequestProperty(name,value)** | **.header(name,value)** hoặc **.setHeader(name,value)** | Trùng header và restricted headers |
| Connect timeout | **setConnectTimeout(milliseconds)** | **HttpClient.Builder.connectTimeout(Duration)** | Không phải total deadline |
| Read timeout | **setReadTimeout(milliseconds)** | **HttpRequest.Builder.timeout(Duration)** | **Không tương đương 1:1** |
| Status | **getResponseCode()** | **response.statusCode()** | Tách HTTP status khỏi transport failure |
| Success body | **getInputStream()** | **BodyHandlers.ofString/ofByteArray/ofInputStream** | Chọn handler theo dung lượng/content |
| Error body | **getErrorStream()** | **response.body()** cho status 4xx/5xx | Legacy error stream có thể null |
| Response header | **getHeaderField("Name")** | **response.headers().firstValue("Name")** | Optional và headers nhiều values |
| Redirect | **setInstanceFollowRedirects(...)** | **followRedirects(Redirect...)** | Defaults khác nhau |
| Cookies | **CookieHandler.setDefault(...)** hoặc manual Cookie | **cookieHandler(CookieHandler)** | Session state không tự chuyển |
| Proxy | **openConnection(proxy)** / system proxy | **proxy(ProxySelector)** | Proxy routing và credentials |
| TLS | **HttpsURLConnection** | **sslContext(...)**, default TLS | Cert chain, hostname, mTLS |
| Async | Tự chạy blocking code trên executor | **sendAsync(...)** | Future, cancellation, backpressure |
| HTTP version | Built-in HTTP connection chủ yếu HTTP/1.1 | HTTP/1.1 và HTTP/2 | Preferred vs actual version |
| Resource cleanup | Close stream + disconnect() | Close streaming response body; quản lý client lifecycle | Không xem close/disconnect là cùng một điều |

**Không xóa HttpURLConnection chỉ vì API cũ.** Nó vẫn hoạt động trong Java 17; quyết định migration phụ thuộc mục tiêu, tương thích JDK, phạm vi HTTP và khả năng test. Dùng checklist để giữ hành vi trước, tối ưu sau.

## 3. Đọc URLConnection legacy đúng cách

Mã cũ tối giản:

~~~java
URL url = new URL("https://service.example/data");
URLConnection conn = url.openConnection();
try (InputStream in = conn.getInputStream()) {
    byte[] bytes = in.readAllBytes();
    String text = new String(bytes, StandardCharsets.UTF_8);
}
~~~

Đây **không phải chương trình độc lập**: cần imports, exception handling và dùng biến text. Nó chỉ thích hợp khi URL handler/response phù hợp, body có giới hạn và charset UTF-8 đúng contract. Với HTTP 404, **getInputStream()** có thể ném **FileNotFoundException** thay vì trả error body; muốn đọc status/error body phải làm việc trực tiếp với **HttpURLConnection**.

### Mẫu legacy xử lý HTTP status và error body

~~~java
HttpURLConnection conn = (HttpURLConnection) url.openConnection();
conn.setConnectTimeout(2_000);
conn.setReadTimeout(3_000);
conn.setInstanceFollowRedirects(false);
conn.setRequestMethod("GET");
try {
    int status = conn.getResponseCode();
    InputStream source = status >= 400
            ? conn.getErrorStream()
            : conn.getInputStream();

    String body = "";
    if (source != null) {
        try (InputStream in = source) {
            body = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
    System.out.println(status + " " + body);
} finally {
    conn.disconnect();
}
~~~

**getErrorStream() có thể null** khi không có error content, chưa kết nối hoặc không có lỗi phù hợp. **getErrorStream() không tự khởi tạo kết nối**; hãy đọc status qua **getResponseCode()** trước. **getInputStream()** có thể trả dữ liệu rỗng trên 204/304. Không cố parse JSON ở status không có response body.

Đừng diễn giải IOException chung thành **HTTP 500**. DNS failure, TLS handshake failure, connection reset hoặc timeout có thể xuất hiện mà **không tồn tại HTTP response**. Ngược lại, HTTP 500 là response mà server/gateway đã gửi.

## 4. GET tương đương với HttpClient

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/data"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

int status = response.statusCode();
String body = response.body();
~~~

Snippet cần imports và catch **IOException/InterruptedException**. **BodyHandlers.ofString(StandardCharsets.UTF_8)** dùng UTF-8 theo API contract. Nếu server công bố một charset khác, cần đọc Content-Type và dùng decoder thích hợp; **Content-Encoding: gzip** không phải text charset.

Mới có thể trả response.statusCode()==404 kèm response.body() là error message. **BodyHandlers.ofString() không tự xem 4xx/5xx là exception.** Thường nên parse error schema dựa trên status, không chỉ return body và coi thành công.

### Phân loại status đúng

~~~java
int code = response.statusCode();
if (code >= 200 && code < 300) {
    // HTTP success; xem mã cụ thể và business contract.
} else if (code >= 300 && code < 400) {
    // Redirect/conditional response; ví dụ 304.
} else if (code >= 400 && code < 500) {
    // Validation/auth/not found/rate limit...
} else if (code >= 500 && code < 600) {
    // HTTP server/gateway error.
}
~~~

**HTTP 202 Accepted** chưa bảo đảm job hoàn thành; **204 No Content** không có body; **304 Not Modified** dùng trong caching; **404 Not Found** có thể là outcome hợp lệ khi tìm tài nguyên; **429** có thể yêu cầu backoff theo Retry-After. **Business success không tương đương mọi 2xx**.

### Bảng lỗi

| Kết quả | Legacy | HttpClient |
| --- | --- | --- |
| 200 có body | getInputStream | response.body() |
| 201 + Location | getResponseCode + getHeaderField | statusCode + headers().firstValue |
| 204 không có content | getResponseCode, body rỗng | statusCode, body rỗng |
| 302 Location | Theo cờ redirect | Theo Redirect.NEVER/NORMAL/ALWAYS |
| 404/500 có error body | getErrorStream có thể có dữ liệu | HttpResponse chứa status và body |
| DNS/connection/TLS failure | IOException/subtype | IOException/subtype; không có HttpResponse hoàn chỉnh |
| Timeout | SocketTimeoutException hoặc IOException tùy phase | HttpTimeoutException/subtype hoặc IOException |
| Request bị interrupt | Thread blocking/IOException tùy vị trí | send có thể throw InterruptedException |

**Nguyên tắc migration:** giữ HTTP status trong **response**, lỗi transport trong **exception**, và lỗi nghiệp vụ trong **domain result**. Không gán status 0 hoặc 500 giả làm HTTP response khi chỉ có IOException.

## 5. Redirect: defaults khác nhau

**HttpURLConnection** có cơ chế theo redirect và mặc định auto-follow thông thường bật; instance có **setInstanceFollowRedirects(false)**. **HttpClient.newHttpClient()** mặc định **HttpClient.Redirect.NEVER**. Nếu legacy từng nhận 200 sau khi tự follow 302, modern mặc định có thể chỉ nhận 302.

~~~java
// Legacy: tắt auto-follow để quan sát 302.
conn.setInstanceFollowRedirects(false);

// Modern: tắt auto-follow để giữ behavior trên.
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

// Khi thực sự muốn follow theo policy:
HttpClient followed = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
~~~

**Redirect.NORMAL** không cho phép downgrade HTTPS → HTTP trong built-in client; **ALWAYS** có policy rộng hơn. Với POST, 301/302/303 có thể dẫn tới thay method theo rules/historical behavior, còn 307/308 yêu cầu giữ method; **test các endpoint có side effect** thay vì giả định client luôn giữ nguyên POST body.

**Không làm mất bảo vệ credentials**: redirect sang origin khác có thể liên quan Authorization/Cookie. Chỉ bật auto-follow nếu việc chuyển domain, protocol và method được kiểm soát theo contract.

## 6. Timeouts không thể đổi theo phép tính đơn giản

Legacy:

~~~java
conn.setConnectTimeout(2000); // ms.
conn.setReadTimeout(3000);    // ms.
~~~

**setConnectTimeout** giới hạn đợi thiết lập connection theo contract. **setReadTimeout** là timeout cho blocking **read** chờ dữ liệu; không phải tổng deadline cho một HTTP request bao gồm mọi byte. Trong URLConnection, **0** thường biểu diễn timeout vô hạn theo Javadoc, không phải tức thời.

Modern:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET().build();
~~~

**connectTimeout** chỉ áp dụng khi cần connection mới; reused connection không phải làm TCP connect lại. **HttpRequest.timeout(Duration)** giới hạn request theo API, **không tương đương từng lần read()** như legacy. Đặc biệt khi dùng **BodyHandlers.ofInputStream**, send hoặc sendAsync có thể trả response khi headers đã đến dù body còn đang mở; ứng dụng cần **body idle timeout, size limit, total deadline và close/cancel** nếu cần.

Khi chuyển, ghi lại **SLA thực**: connect deadline, time to headers, body idle timeout, total operation deadline. Không chỉ đổi milliseconds thành Duration rồi cho rằng hành vi giữ nguyên.

Khi bắt **InterruptedException** từ **send()**, gọi **Thread.currentThread().interrupt()** và truyền cancellation/lỗi lên tầng gọi. Cancellation không chắc khiến server rollback nếu request đã gửi.

## 7. POST: OutputStream vs BodyPublisher

Legacy POST:

~~~java
HttpURLConnection conn = (HttpURLConnection) url.openConnection();
conn.setRequestMethod("POST");
conn.setDoOutput(true);
byte[] bytes = "ping".getBytes(StandardCharsets.UTF_8);
conn.setFixedLengthStreamingMode(bytes.length);
conn.setRequestProperty("Content-Type", "text/plain; charset=UTF-8");
try (OutputStream out = conn.getOutputStream()) {
    out.write(bytes);
}
int code = conn.getResponseCode();
~~~

Snippet cần xử lý closing response streams, finally disconnect và imports. **setFixedLengthStreamingMode** sử dụng **byte count**, không phải **String.length()** (số UTF-16 code units). Sử dụng **setChunkedStreamingMode** thay thế khi độ dài chưa biết có thể ảnh hưởng đến auto-auth/redirect trong legacy; streaming mode có thể làm phát sinh **HttpRetryException** trong trường hợp cần tự replay.

Modern POST:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "text/plain; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                "ping", StandardCharsets.UTF_8))
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

Các **BodyPublishers** phù hợp gồm:

| Publisher | Khi dùng |
| --- | --- |
| **noBody()** | Request không có body |
| **ofString(text, charset)** | JSON hoặc text đã có |
| **ofByteArray(bytes)** | Dữ liệu nhị phân nhỏ |
| **ofFile(path)** | Upload file |
| **ofInputStream(supplier)** | Nguồn stream có thể tạo khi gửi |
| **fromPublisher(...)** | Reactive Flow.Publisher<ByteBuffer> |

**Không tự đặt header Content-Length** cho mọi publisher. Built-in HttpClient có restricted headers và tự quản lý framing theo publisher/protocol; chuyển legacy **setRequestProperty("Content-Length", ...)** sang modern **.header("Content-Length", ...)** có thể bị từ chối. Để gửi Unicode, Content-Length theo byte UTF-8, không theo số Java characters.

**Replayability:** Supplier trong **ofInputStream** có thể phải tạo stream mới nếu client cần gửi lại nội dung khi xử lý authentication/retries. Đừng trả cùng một InputStream đã bị consume; request sau có thể gửi thiếu byte.

**Idempotency:** Nếu POST tạo đơn hàng đã được commit nhưng client timeout khi chờ response, retry tự động có thể tạo order thứ hai. Thay API client không giải quyết vấn đề đó: cần idempotency key/business transaction ID theo API contract, hoặc tra cứu trạng thái trước khi thử lại.

## 8. Header, charset, Content-Encoding và cookies

### Charset không tự đồng nhất

~~~java
String textLegacy = new String(bytes, StandardCharsets.UTF_8);
HttpResponse<String> textModern = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
~~~

Hai mẫu tương đương **nếu contract của endpoint là UTF-8**. Nếu server công bố charset khác, cần phân tích **Content-Type**; không phụ thuộc default charset của hệ điều hành. **Content-Encoding** như gzip là compression/content coding khác **charset** của text; **Content-Length** là số byte, không phải Java String.length().

Với binary response, dùng **BodyHandlers.ofByteArray()**, **ofInputStream()**, **ofFile(path)**. Đừng chuyển JPEG/ZIP thành String rồi chuyển về byte, vì có thể hỏng dữ liệu. **ofByteArray** giữ toàn body trong RAM nên cần size limit; **ofFile** có thể lưu **error body của 404/500** vào file nếu dùng trực tiếp, phải kiểm tra status.

### Multiple headers

Legacy **getHeaderField("Set-Cookie")** có thể chỉ đưa một value. Modern **response.headers().allValues("Set-Cookie")** lấy danh sách; không gộp mọi Set-Cookie bằng dấu phẩy. **HttpRequest.Builder.header(...)** thêm header value; **setHeader(...)** thay các value trước đó. Điều này khác việc legacy setRequestProperty thay một giá trị.

### Cookies

Legacy có thể dùng CookieManager qua **CookieHandler.setDefault(...)** toàn JVM hoặc tự đặt Cookie header. Modern có thể cấu hình cụ thể cho client:

~~~java
CookieManager cookies = new CookieManager();
cookies.setCookiePolicy(CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookies)
        .build();
~~~

Snippet cần imports. Không kỳ vọng mọi HttpClient tự giữ session cookies nếu không cấu hình handler phù hợp. Chỉ chấp nhận cookies theo domain/path/security policy; tránh log secret cookies.

### Authentication và proxy

Legacy có thể dùng **Authenticator.setDefault(...)**, **url.openConnection(proxy)**, cấu hình JVM system properties hoặc headers. Modern có **HttpClient.Builder.authenticator(...)** và **proxy(ProxySelector)**. Xác minh proxy credentials, HTTP 401/407, Cookie, Authorization, redirect cross-origin và DNS/TLS. Không hard-code password trong source và không chuyển Authorization nhạy cảm theo redirect tùy tiện.

## 9. HttpsURLConnection và HTTPS của HttpClient

**HttpsURLConnection** kế thừa HttpURLConnection và có cấu hình cho SSL socket factory/hostname verifier. **HttpClient** dùng SSLContext mặc định hoặc **HttpClient.Builder.sslContext(...)**, có thể cung cấp SSLParameters cho các yêu cầu thích hợp.

Khi chuyển, kiểm tra:

- Truststore/trust anchors có còn đúng?
- Certificate chain, SAN/hostname và TLS versions/cipher có tương thích?
- Có mutual TLS và KeyManager phù hợp không?
- Proxy CONNECT tunneling thay đổi đường đi hay không?
- Có code legacy dùng TrustManager accept-all hoặc HostnameVerifier always true không?

**Không giữ lại cấu hình trust-all hay tắt hostname verification** chỉ để “bảo đảm tương đương”. Nếu mã cũ không xác minh chứng chỉ đúng, đó là rủi ro bảo mật cần sửa, không phải behavior đáng giữ.

**HTTPS handshake failure khác HTTP status 5xx.** Nếu TLS certificate bị từ chối, client có thể ném SSLHandshakeException mà chưa có HttpResponse. Log nguyên nhân và không tự gán 500/503.

## 10. Connection reuse, tài nguyên và streaming response

**HttpURLConnection** là handle request, nhưng underlying persistent connection có thể dùng chung. Javadoc nói **disconnect()** báo các request tiếp theo tới server khó xảy ra sớm; nó có thể đóng socket idle, không đảm bảo ngay lập tức đóng tất cả connections. Đọc/đóng InputStream/OutputStream bằng **try-with-resources** và gọi disconnect trong finally là cách diễn đạt ownership tốt.

**HttpClient** sau build có thể chia sẻ và tái sử dụng. Với **Java 17**, HttpClient **chưa kế thừa AutoCloseable**, nên mã biên dịch **--release 17** không bọc HttpClient bằng try-with-resources; Java 21+ mới bổ sung close/shutdown APIs. Trên Java 17, quản lý client lâu dài và body resources theo handler.

### BodyHandlers ofInputStream: trách nhiệm đã chuyển sang caller

~~~java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = input.read(buffer)) != -1) {
        // Xử lý với size limit/backpressure.
    }
}
~~~

**HttpResponse<InputStream>** có thể được trả khi mới đọc xong headers; **body vẫn còn đang truyền**. Caller phải **read đến EOF hoặc close stream** nếu không cần tiếp tục. Nếu bỏ quên, HTTP connection/resources có thể bị giữ và không reuse đúng. Tương tự **BodyHandlers.ofLines()** cần duyệt/close Stream<String>, **ofPublisher()** cần subscribe/request hoặc cancel subscription.

**Không luôn dùng readAllBytes()** với response dài/vô hạn. Hãy có max bytes, read timeouts, idle deadline, decompression limits và cleanup. **Đóng sớm** có thể khiến HTTP/1.1 connection không được reuse, nhưng vẫn là đúng khi caller đã hủy tải.

### HTTP/2

Built-in **HttpURLConnection** truyền thống chủ yếu dùng HTTP/1.1; **HttpClient** có HTTP/1.1 và HTTP/2. Java 17 HttpClient **mặc định ưu tiên HTTP/2**, nhưng actual version phụ thuộc server, proxy và TLS. Để test migration giữ protocol tương đương, có thể dùng:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();
~~~

Sau đó kiểm tra **response.version()** thay vì suy từ client.version(). Khi đã đạt parity, bật HTTP/2 preference là thay đổi riêng cần benchmark/observability.

## 11. Async: sendAsync không tự giải quyết nghiệp vụ

Mã legacy có thể gọi HttpURLConnection trong executor để chạy bất đồng bộ. HttpClient có:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

CompletableFuture<String> result =
        future.thenApply(response -> {
            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "HTTP " + response.statusCode());
            }
            return response.body();
        });
~~~

Đây là snippet cần imports và biến client/request. **CompletableFuture** có thể complete exceptionally, **join()** có thể bọc nguyên nhân trong **CompletionException**. Thực hiện background transformation nặng trên một bounded executor riêng thay vì block callback/network executor không kiểm soát.

**Cancellation** best-effort: hủy future không bảo đảm server chưa nhận request hay đã rollback. Nếu HTTP exchange đã trả streaming InputStream, cancel outer future sau khi completed **không thay thế input.close()**. Với lượng request lớn, cần bounded concurrency/rate limits; async không tự tạo backpressure cho nghiệp vụ.

**Đừng chuyển sync sang async cùng lúc với việc đổi cookie, auth, redirect, HTTP version và retry**, vì khó tìm nguyên nhân nếu regression xảy ra. Một chiến lược an toàn là chuyển sync trước với behavior parity rồi tối ưu async sau.

## 12. Ví dụ Java 17 hoàn chỉnh: legacy và modern trả cùng kết quả

Ví dụ độc lập dưới đây tự tạo một HTTP server cục bộ bằng **com.sun.net.httpserver.HttpServer** (module **jdk.httpserver**), bind **127.0.0.1** với port do OS cấp, không đòi hỏi Internet. Từng endpoint được gửi qua **HttpURLConnection** và **HttpClient**:

- GET **/ok** → **200 OK** và text **OK**.
- GET **/missing** → **404** và error body **NOT_FOUND**.
- GET **/redirect** → **302** và **Location: /ok**, **không follow** ở cả hai client.
- GET **/empty** → **204** với body rỗng.
- POST **/echo** với body **ping** → **201** với **RECEIVED:ping**.

Để kiểm tra behavior parity trước, HttpClient chọn **HTTP_1_1** và **Redirect.NEVER**; legacy đặt **setInstanceFollowRedirects(false)**. Charset là UTF-8 và response bodies rất nhỏ nên demo có thể đọc toàn bộ bytes. Trong production, API cần streaming/size limits.

### HttpMigrationComparisonDemo.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpMigrationComparisonDemo {
    record Result(int status, String body, String location) {}

    static void respond(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        if (code == 204 || code == 304 || code == 302) {
            exchange.sendResponseHeaders(code, -1);
            return;
        }
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    static void route(HttpExchange exchange) throws IOException {
        try (exchange) {
            String path = exchange.getRequestURI().getPath();
            switch (path) {
                case "/ok" -> respond(exchange, 200, "OK");
                case "/missing" -> respond(exchange, 404, "NOT_FOUND");
                case "/redirect" -> {
                    exchange.getResponseHeaders().set("Location", "/ok");
                    respond(exchange, 302, "");
                }
                case "/empty" -> respond(exchange, 204, "");
                case "/echo" -> {
                    if (!"POST".equals(exchange.getRequestMethod())) {
                        respond(exchange, 405, "METHOD_NOT_ALLOWED");
                    } else {
                        byte[] data = exchange.getRequestBody().readNBytes(1024);
                        respond(exchange, 201, "RECEIVED:"
                                + new String(data, StandardCharsets.UTF_8));
                    }
                }
                default -> respond(exchange, 404, "NOT_FOUND");
            }
        }
    }

    static Result legacy(URI uri, String method, String content)
            throws IOException {
        URL url = uri.toURL();
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setConnectTimeout(2000);
        conn.setReadTimeout(2000);
        conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod(method);
        try {
            if ("POST".equals(method)) {
                byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
                conn.setDoOutput(true);
                conn.setFixedLengthStreamingMode(bytes.length);
                conn.setRequestProperty(
                        "Content-Type", "text/plain; charset=UTF-8");
                try (OutputStream output = conn.getOutputStream()) {
                    output.write(bytes);
                }
            }

            int status = conn.getResponseCode();
            InputStream bodyStream = status >= 400
                    ? conn.getErrorStream()
                    : conn.getInputStream();
            String body = "";
            if (bodyStream != null) {
                try (InputStream input = bodyStream) {
                    body = new String(input.readAllBytes(),
                            StandardCharsets.UTF_8);
                }
            }
            String location = conn.getHeaderField("Location");
            return new Result(status, body, location);
        } finally {
            conn.disconnect();
        }
    }

    static Result modern(HttpClient client, URI uri, String method,
                         String content) throws IOException, InterruptedException {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3));
        if ("POST".equals(method)) {
            builder.header("Content-Type", "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            content, StandardCharsets.UTF_8));
        } else {
            builder.GET();
        }
        HttpResponse<String> response = client.send(
                builder.build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        return new Result(response.statusCode(), response.body(),
                response.headers().firstValue("Location").orElse(null));
    }

    static void printResult(String label, Result result) {
        String details = " status=" + result.status();
        if (result.location() != null) {
            details += " location=" + result.location();
        } else {
            details += " body=" + result.body();
        }
        System.out.println(label + details);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/", HttpMigrationComparisonDemo::route);
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            for (String path : new String[]{
                    "ok", "missing", "redirect", "empty", "echo"}) {
                String method = "echo".equals(path) ? "POST" : "GET";
                String content = "echo".equals(path) ? "ping" : "";
                URI uri = base.resolve(path);
                printResult("legacy " + path,
                        legacy(uri, method, content));
                printResult("modern " + path,
                        modern(client, uri, method, content));
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Biên dịch và thực thi

Lưu nội dung trên thành file **HttpMigrationComparisonDemo.java** trong thư mục học tập tạm. Dùng JDK 17+ đầy đủ có module **jdk.httpserver**:

~~~bash
javac --release 17 -encoding UTF-8 HttpMigrationComparisonDemo.java
java HttpMigrationComparisonDemo
~~~

**Stdout đã biên dịch với --release 17 và chạy thực tế trên JDK 24.0.2:**

~~~text
legacy ok status=200 body=OK
modern ok status=200 body=OK
legacy missing status=404 body=NOT_FOUND
modern missing status=404 body=NOT_FOUND
legacy redirect status=302 location=/ok
modern redirect status=302 location=/ok
legacy empty status=204 body=
modern empty status=204 body=
legacy echo status=201 body=RECEIVED:ping
modern echo status=201 body=RECEIVED:ping
~~~

**Giải thích:**

1. **/ok:** cả hai API nhận cùng status/body.
2. **/missing:** legacy phải chọn **getErrorStream()** còn modern dùng **response.body()** theo BodyHandler cho status 404. Đây là chỗ thường làm hỏng error handling khi migration.
3. **/redirect:** cả hai đã explicit không follow, nên nhìn thấy status 302 và Location. Nếu dùng defaults khác nhau, có thể legacy tự follow thành 200 trong khi modern vẫn 302.
4. **/empty:** status 204 không có body; đừng parse JSON.
5. **/echo:** legacy setDoOutput + fixed-length bytes + OutputStream; modern BodyPublishers.ofString; server nhận cùng body và trả 201.
6. **HttpClient.Version.HTTP_1_1** làm regression test không lẫn thay đổi protocol H2. Khi bật H2, kiểm tra response.version(), latency, proxy và TLS/ALPN riêng.

**Giới hạn demo:** HttpServer chỉ là test fixture không có TLS, không hỗ trợ mọi HTTP versions, không kiểm thử auth/cookies/compression/proxy. Các status và body cố định trong ví dụ, nên stdout dễ đối chiếu; hệ thống thật cần timeouts, limits, metrics và tests rộng hơn.

## 13. Chiến lược chuyển mã an toàn

### Kiểm kê hành vi trước khi viết lại

Với từng endpoint, ghi rõ:

| Nhóm | Câu hỏi cần trả lời |
| --- | --- |
| URL/URI | Query được encode ra sao? Host, port, scheme, redirects? |
| Method | GET/POST/PUT/PATCH/DELETE nào? Có custom method? |
| Body | UTF-8, bytes, file, stream, fixed-length, chunked, replayable? |
| Headers | Content-Type, Authorization, Cookie, Accept-Encoding, duplicated values? |
| Status | 2xx/3xx/4xx/5xx nào là expected domain outcome? |
| Error body | Code cũ có đọc getErrorStream? Body có schema riêng? |
| Redirect | Auto-follow không? Có thay method/cross-origin? |
| Timeout | Connect, read, total, idle deadline? |
| Cookies/auth | CookieManager, Authenticator, mTLS, token rotation? |
| Proxy/TLS | Proxy selector, truststore, hostname verification? |
| Resources | Ai đóng stream, disconnect, file handles? |
| Recovery | Retry, cancellation, idempotency, observability? |

### Các bước đề xuất

1. **Tách HTTP-only code** khỏi những URLConnection dùng file:/jar:. Không ép toàn bộ về HttpClient.
2. **Viết contract tests** cho cùng URI/method/headers/body, status/error body, redirect, UTF-8, streaming, cookie, TLS và timeouts.
3. **Xây một HttpClient theo policy** (proxy, cookie handler, auth, SSLContext, connect timeout, redirect, HTTP version); tái sử dụng instance.
4. **Xây HttpRequest rõ ràng**, tránh bắn nhiều requests chỉ để đọc error body; chọn BodyPublisher đúng content/size/replayability.
5. **Xử lý HttpResponse theo status**, giữ domain errors riêng, chọn BodyHandler tương ứng và đóng streaming body.
6. **Giữ redirect và HTTP_1_1 trong regression test** nếu muốn so hành vi cũ trước khi thử HTTP/2 hoặc async.
7. **Rollout nhỏ có feature flag**, log status thực, exception/cause, actual HTTP version, latency và redirect path; không log secret.
8. **Đánh giá performance và HTTP/2/async** sau khi đã có behavior parity; rollout/rollback độc lập với việc đổi API.

### Test cases thiết yếu

- **200/201/202/204/206**: body có/không, Location, async job.
- **301/302/303/304/307/308**: redirect, cache, method preservation.
- **400/401/403/404/409/429/500/502/503/504**: error body, auth, Retry-After.
- **Unicode UTF-8, khác charset, binary, gzip**.
- **Large/slow body** và truncated response.
- **Proxy/HTTPS, mTLS, credential header, cookie persistence**.
- **Connect timeout, request timeout, read-body idle timeout**.
- **POST commit nhưng mất response**, kiểm tra idempotency.
- **Async cancellation** và close resources.
- **Reused connections** và actual protocol version.

**Đừng chỉ test happy path 200**: hai API thường giống nhau ở trường hợp đơn giản; các khác biệt gây lỗi production thường ở 404/error body, 302, auth, streaming và timeouts.

## 14. Lỗi phổ biến và cách tránh

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng exception để bắt HTTP 404 của HttpClient | Không vào catch vì 404 là response | response.statusCode() |
| Bỏ getErrorStream ở legacy | Mất error body | Đọc status rồi error stream nếu có |
| Không đặt redirect policy | Defaults khác, behavior thay đổi | Explicit NEVER/NORMAL, test 3xx |
| Coi readTimeout như request timeout | Deadline sai | Định nghĩa connect/total/body idle riêng |
| Dùng new String(bytes) không charset | Lỗi Unicode theo OS | Charset theo Content-Type/contract |
| Tự set Content-Length bất kể body publisher | Header bị restricted hoặc size sai | Giao cho BodyPublisher |
| Dùng String.length làm byte count | Content length sai với Unicode | Tính bytes UTF-8 |
| Giữ URLConnection cast HTTP cho file: | ClassCastException | Tách protocols |
| Tạo client mới cho mỗi request | Không tận dụng reuse tốt | Shared HttpClient |
| Chuyển cookies qua mặc định mà không cấu hình | Mất session | CookieHandler/cookie store |
| Chuyển TrustManager accept-all | Lỗ hổng MITM | TLS validation chuẩn |
| Nhận 503 rồi gọi đó là IOException | Gộp HTTP và network failure | Tách status và exception |
| Đọc file lớn với ofByteArray | Dễ OOM | Streaming handler + limits |
| Quên đóng ofInputStream body | Leak resources | try-with-resources |
| Retry POST khi timeout không kiểm tra state | Duplicated operations | Idempotency key + status inquiry |
| Dùng try(HttpClient...) với --release17 | Không compile | Java 17 chưa có AutoCloseable HttpClient |
| Fire-and-forget sendAsync hàng loạt | Queue và resource exhaustion | Bounded concurrency/backpressure |
| Dùng URLEncoder cho toàn URL | Sai path/query semantics | Encode riêng URI components |

## 15. Bài tập tự kiểm tra

1. Vì sao **URLConnection** và **HttpURLConnection** không phải cùng một type? Có URL scheme nào cast thất bại?
2. Những setter legacy nào phải gọi trước **getOutputStream/getResponseCode**?
3. So sánh **getInputStream/getErrorStream** với **BodyHandlers.ofString** khi server trả 404 có JSON error body.
4. Legacy mặc định follow redirects, modern default NEVER. Một GET 302 Location /v2 cho ra gì nếu giữ defaults?
5. Vì sao **setReadTimeout(3000)** không đồng nghĩa **HttpRequest.timeout(3s)**?
6. Tại sao Content-Length phải tính theo bytes khi POST body có tiếng Việt?
7. Chuyển một POST legacy có **setDoOutput(true)** sang **BodyPublishers.ofByteArray** và kiểm tra Content-Type.
8. Nếu dùng **BodyPublishers.ofInputStream**, supplier phải hỗ trợ việc gì khi request bị replay?
9. **BodyHandlers.ofFile** trả file khi status 404. Có phải download thành công không? Vì sao?
10. Khi nào nên dùng **HttpClient.Version.HTTP_1_1** để so parity và khi nào bật HTTP/2?
11. Vì sao **CookieHandler.setDefault** từ mã cũ không nên được giả định tự gắn đúng vào mọi HttpClient mới?
12. Một POST đã commit nhưng HttpClient.send() ném IOException trước khi nhận response. Retry có an toàn không?
13. Chạy **HttpMigrationComparisonDemo** và đối chiếu 10 dòng stdout; thử đổi redirect policy rồi ghi nhận khác biệt.
14. Mở rộng demo thêm status 503 có error body và Retry-After. Xử lý đúng trong cả hai API.
15. Thiết kế regression tests cho ứng dụng có HTTPS/mTLS, proxy và Unicode; không dùng trust-all để cho test qua.

## 16. Checklist trước khi merge

- [ ] Chỉ chuyển các URLConnection thực sự dùng HTTP/HTTPS?
- [ ] Đã xác định method, URL encoding, headers, charset, request/response body?
- [ ] Đã xử lý 4xx/5xx qua status và body chứ không qua IOException?
- [ ] Đã giữ redirect behavior theo contract và kiểm tra method preservation?
- [ ] Đã phân biệt connect, read, total request và body idle timeouts?
- [ ] Có CookieHandler, Authenticator, proxy, SSLContext đúng?
- [ ] Không vô hiệu hóa TLS hostname/certificate validation?
- [ ] Có streaming body ownership và size limits?
- [ ] Có kiểm soát retry/idempotency cho request tạo side effect?
- [ ] Có test status 204/304/404/429/503, Unicode và truncated response?
- [ ] Có xem response.version() khi đổi HTTP/1.1 sang HTTP/2?
- [ ] Có log/tracing, regression metrics và rollback khi production khác dự kiến?
- [ ] Mã Java biên dịch với phiên bản target thực, không dùng API Java 21+ dưới --release 17?

**Kết luận:** **URLConnection/HttpURLConnection** gộp trạng thái request và connection, có success/error streams, redirect và timeout semantics riêng. **java.net.http.HttpClient** tách client policy, request và typed response, cung cấp HTTP/2 và async. Một migration đúng phải **giữ hành vi HTTP và business contract**: status, error body, redirect, charset, request bytes, timeout, TLS, proxy, cookies, streaming resources và idempotency. Code ngắn hơn chưa đủ: phải có **tests và observability** chứng minh tương đương.

### Tài liệu chính thức

- [URLConnection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html)
- [HttpURLConnection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html)
- [HttpsURLConnection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html)
- [HttpClient — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpRequest — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [HttpRequest.BodyPublishers — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [HttpResponse — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html)
- [HttpResponse.BodyHandlers — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [HttpServer — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
