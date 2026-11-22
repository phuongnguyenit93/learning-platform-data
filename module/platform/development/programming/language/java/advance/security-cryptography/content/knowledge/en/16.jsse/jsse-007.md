# 16.7. HttpsURLConnection, HttpClient và ranh giới cấu hình SSLContext hoặc xác minh hostname

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt hai HTTP(S) client tích hợp JDK: **`HttpsURLConnection`** (kiểu kết nối truyền thống trong `java.net`) và **`java.net.http.HttpClient`** (API HTTP hiện đại từ Java 11, dùng được với Java 17+).
2. Chỉ ra trách nhiệm của **`SSLContext`, `KeyManagerFactory`, `TrustManagerFactory`, truststore, keystore, TLS handshake, kiểm certificate chain và kiểm hostname/SAN** trong mỗi client.
3. Hiểu **gắn một `SSLContext` tùy chỉnh không tự có nghĩa tắt hoặc thay hostname verification**; và một certificate chain hợp lệ vẫn phải khớp tên endpoint trong URL.
4. Cấu hình **trust anchors theo từng HTTP client** mà không tắt xác minh chứng thư; biết chỗ nào có thể tùy chỉnh `SSLSocketFactory` hoặc `HostnameVerifier` và chỗ nào API **không** có hook tương đương.
5. Nhận diện nguy cơ **global defaults**, trust-all managers, hostname-verifier luôn true, certificate pinning sai cách, cấu hình mTLS thiếu khóa riêng hoặc chọn nhầm danh tính.
6. Chạy lab **Java 17+** tạo root/leaf X.509 bằng `keytool`, khởi động HTTPS server cục bộ và gọi bằng cả hai API với **cùng `SSLContext` tin CA**, xác nhận cả hai nhận được phản hồi HTTPS đã được JSSE bảo vệ.
7. Thiết kế luồng kiểm tra khi gặp `SSLHandshakeException`/`PKIX path building failed`/hostname mismatch mà không “chữa lỗi” bằng cách bỏ bảo mật.

**Phạm vi:** Bài thuộc **Java Advance – security-cryptography / 16. JSSE**. Chủ đề chính là **ranh giới cấu hình TLS và xác minh hostname ở hai HTTP clients**. Đoạn lab dùng CA tự tạo để học, không thiết lập PKI production, OAuth hay authorization hoàn chỉnh.

---

## 1. Vấn đề kỹ thuật: Có `https://` chưa đủ để hiểu cấu hình bảo mật

Trong Java 17, cùng một endpoint:

```text
https://api.example.com/orders
```

có thể được gọi qua hai cách:

```java
// API truyền thống:
HttpsURLConnection connection =
        (HttpsURLConnection) new URL(url).openConnection();

// API hiện đại:
HttpClient client = HttpClient.newHttpClient();
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
```

Đây là **các đoạn minh họa chưa độc lập**: cần import kiểu tương ứng, tạo biến `url`/`request`, xử lý checked exception và đóng/đọc response đúng cách. Phần code chạy đầy đủ ở mục 8.

Hai API đều có thể dùng **JSSE (Java Secure Socket Extension)** để thiết lập TLS, nhưng cách cấu hình và lifetime khác nhau. **Không thể suy ra hai API chia sẻ cùng trạng thái TLS hoặc cùng hooks chỉ vì cùng chạy trong một JVM.**

### 1.1. Điều gì phải được bảo đảm khi truy cập HTTPS?

Khi client kết nối đến một server HTTPS:

1. URL chỉ rõ **scheme `https`**, host, port, path, query.
2. Kết nối TLS phải thương lượng phiên bản/cipher suites phù hợp.
3. Server cung cấp chứng thư X.509 và các thành phần chain cần thiết.
4. Trust manager kiểm chain đến **trust anchor** được client chấp thuận, các ràng buộc PKIX/purpose/validity theo policy.
5. Client kiểm **hostname hoặc IP literal của endpoint dự định** khớp Subject Alternative Name (SAN) theo quy tắc HTTPS.
6. TLS handshake kiểm server thực sự sở hữu private key tương ứng, xác thực transcript/`Finished` và thiết lập traffic keys.
7. HTTP request/response chạy trên TLS channel đã được xác thực và bảo vệ record integrity/confidentiality.
8. Ứng dụng còn phải kiểm **authentication/authorization** nghiệp vụ, content-type/size, redirects, SSRF, dữ liệu nhận và key/certificate lifecycle.

**Hai phép kiểm dễ bị nhầm:** (4) *certificate chain trusted* và (5) *certificate dành cho host đang truy cập* là **hai điều kiện riêng**. Nếu bạn tạo `SSLContext` chỉ tin đúng một CA nhưng tắt hostname checking, attacker có certificate khác do CA đó ký có thể bị nhầm là đúng server theo rủi ro và policy của hệ thống.

### 1.2. Sơ đồ các lớp

```text
             URL: https://api.example.com:443/path
                               │
               HTTP client (URL, host, redirects, proxy)
                               │
              TLS configuration / SSLContext
                  ┌────────────┴────────────┐
                  │                         │
             KeyManagers              TrustManagers
       (private key của client)   (trust anchors của peer)
                  │                         │
                  └────────────┬────────────┘
                               │
                JSSE validates certificate path
                               │
             HTTPS endpoint identity / SAN check
                               │
              TLS handshake + authenticated keys
                               │
                      HTTPS request/response
                               │
                       Application policy
```

Sơ đồ trình bày **trách nhiệm logic**, không phải thứ tự từng lời gọi nội bộ của một provider. Một số kiểm tra certificate chain/hostname nằm trong cùng luồng trust manager có tham số socket/engine.

---

## 2. Bảng so sánh `HttpsURLConnection` và `HttpClient` trong Java 17

| Tiêu chí | `HttpsURLConnection` | `java.net.http.HttpClient` |
| --- | --- | --- |
| Package | `javax.net.ssl.HttpsURLConnection` (mở từ `java.net.URL`) | `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse` |
| Phong cách | Mỗi connection/URL, gọi `getInputStream`, `getResponseCode`... | Client tái sử dụng, request/response kiểu builder, có `send`/`sendAsync` |
| HTTP versions | API legacy thường dùng HTTP/1.1; hành vi phụ thuộc handler | HTTP/1.1 và HTTP/2 khi hỗ trợ; chọn qua `HttpClient.Version` |
| TLS mặc định | JSSE và default SSLSocketFactory/hostname verifier theo cấu hình | JSSE và SSLContext mặc định nếu không cung cấp; HTTP stack quản lý TLS/identity |
| SSLContext riêng | Không có `connection.setSSLContext(...)`; dùng `context.getSocketFactory()` qua `setSSLSocketFactory` | `HttpClient.newBuilder().sslContext(context)` |
| Truststore riêng | Tạo trust manager/context rồi cài socket factory cho connection | Tạo trust manager/context rồi gắn vào builder của client |
| Client certificate cho mTLS | KeyManagers trong SSLContext dùng tạo socket factory | KeyManagers trong SSLContext của HttpClient |
| Hostname verification | Có hook `setHostnameVerifier` và default verifier; **không nên tắt** | **Không có public builder API `setHostnameVerifier` tương ứng**; giữ endpoint identification của HTTP client |
| Scope cấu hình | `setSSLSocketFactory`/`setHostnameVerifier` trên từng instance; `setDefault...` là các default process-wide cho future instances | `sslContext(...)`/`sslParameters(...)` gắn khi build một `HttpClient`; tái sử dụng client phù hợp |
| Connection reuse | Handler có thể keep-alive, cần đọc/đóng response đúng | Connection pooling và HTTP/2 multiplexing do client quản lý; nên tái sử dụng thay vì tạo một client/request |
| Redirects | Tùy `setInstanceFollowRedirects` và handler | `followRedirects(NORMAL/ALWAYS/NEVER)`; mặc định `NEVER` |
| Timeout | `setConnectTimeout` và `setReadTimeout` | `connectTimeout` trên client, `timeout` trên request; asynchronous cancellation theo semantics riêng |
| Asynchronous API | Chủ yếu blocking | `sendAsync` trả `CompletableFuture` |
| Tùy biến proxy | `openConnection(Proxy)` hoặc JVM handler policy | `proxy(ProxySelector)` trên builder |
| Cần lưu ý | Global defaults, instance lifetime, input/error stream, redirect & response ownership | Cấu hình client dùng chung, pooling, async, proxy/HTTP2, không dựa vào internal flags vô hiệu hostname |

**Một `SSLContext` có thể được dùng bởi cả hai API**, nhưng mỗi API vẫn giữ cấu hình HTTP/hostname/redirect/proxy của riêng nó. Không phải tất cả behavior, TLS session reuse, ALPN hoặc HTTP/2 đều giống nhau sau khi cùng cài một context.

### 2.1. Vì sao có hai APIs?

`HttpsURLConnection` là lựa chọn lâu đời: dễ áp dụng cho HTTP call đơn giản, nhiều ứng dụng Java legacy, framework cũ và proxy/URL handler truyền thống. `HttpClient` là API hiện đại: request builders, response handlers, reusable clients, async, HTTP/2 và chính sách redirect/timeouts rõ ràng.

Đừng đổi API chỉ vì tin rằng “HttpClient luôn bảo mật hơn” hoặc “HttpsURLConnection luôn bỏ kiểm hostname”. **Cả hai có thể xác minh TLS an toàn nếu cấu hình đúng; cả hai có thể bị phá nếu bạn dùng trust-all, không bảo vệ key hoặc thao tác URL/proxy sai.**

---

## 3. `SSLContext` làm gì và không làm gì?

Trong JSSE, `SSLContext` kết hợp:

- **`KeyManager[]`**: chọn private key/certificate identity của **chính phía này** khi TLS cần client authentication (với HTTP client) hoặc server authentication (với HTTPS server).
- **`TrustManager[]`**: xác minh chứng thư **phía đối tác** dựa trên trust anchors và policy.
- **`SecureRandom`**: nguồn ngẫu nhiên thích hợp cho hoạt động TLS của provider.
- Các tham số/triển khai TLS do JSSE/provider quản lý.

Khởi tạo sơ lược:

```java
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, new SecureRandom());
```

Đây là **đoạn code minh họa chưa độc lập**, cần imports `javax.net.ssl.SSLContext`, `java.security.SecureRandom` và các biến `keyManagers`, `trustManagers` đã được cấu hình. Chữ `"TLS"` chọn engine giao thức TLS; **không có nghĩa ứng dụng tự đặt SSL version, hostname hoặc trust policy an toàn** chỉ với một dòng code.

### 3.1. `SSLContext` không tự quyết định URL đích

Trong ứng dụng HTTPS:

- URL/request xác định hostname dự định truy cập;
- context định nghĩa key/trust infrastructure;
- HTTP/TLS client quyết định cách kết hợp **hostname trong URL** với chứng thư trong handshake.

Nếu bạn dùng `SSLContext` tùy chỉnh, **đừng mặc nhiên suy ra hostname verification bị tắt**. Và cũng đừng suy ra một `SSLContext` trả về từ API là đủ để xác minh hostname nếu dùng **raw `SSLSocket`** không cấu hình endpoint identification. Ranh giới chính là **ai có hostname dự định và ai áp dụng quy tắc endpoint identity**.

### 3.2. Truststore và keystore khác nhau

```text
HTTPS client one-way:
    Truststore: CA/root hoặc server certificate được chấp nhận
    KeyStore:   thường KHÔNG cần client private key

HTTPS client dùng mTLS:
    Truststore: CA/root tin server
    KeyStore:   client private key + client cert chain

HTTPS server:
    KeyStore:   server private key + server cert chain
    Truststore: CA/root tin client nếu server yêu cầu mTLS
```

**Không copy server private key sang client truststore.** Truststore có trust anchors/certificates công khai, nhưng integrity của nó quan trọng; keystore có private material phải bảo vệ khỏi bị đọc/ghi trái phép.

`KeyManagerFactory` và `TrustManagerFactory` là hai phần khác nhau:

```java
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identityStore, password);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);
```

Đây là **mã minh họa chưa độc lập** cần imports, các biến và exception handling. Với one-way HTTPS client không cần identity key, có thể truyền `null` cho key managers khi `SSLContext.init(...)`, nhưng vẫn cần trust managers hợp lệ.

### 3.3. `tmf.init(customStore)` thường thay tập trust anchors, không tự cộng thêm

Một lỗi thực tế là ứng dụng cần tin CA nội bộ và làm:

```java
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(internalTrustStore);
```

Sau đó ngạc nhiên vì public HTTPS sites không còn được chấp nhận. **Khi khởi tạo từ một KeyStore chỉ có CA nội bộ, trust manager thường tin các anchors của store đó**, không tự động hợp nhất với truststore mặc định của JDK.

Các lựa chọn thiết kế:

1. **Tách client theo trust domain:** một `HttpClient` chỉ tin internal CA; một client khác dùng default trust anchors cho public Internet.
2. **Tạo truststore được quản lý chứa chính xác những roots cần tin:** merge có kiểm soát từ nguồn đáng tin, cập nhật theo lifecycle; không thêm tùy tiện mỗi CA nhận được qua mạng.
3. **Đưa ra quyết định tin cậy dựa trên policy/protocol cụ thể** nếu tổ chức yêu cầu pinning hoặc custom PKIX, ưu tiên thư viện/provider đã được đánh giá.

**Đừng** tự viết một `X509TrustManager` “thử tất cả, hễ một cái không lỗi thì tin” nếu không hiểu endpoint/algorithm constraints, exception handling và trust scope. Một custom trust manager có thể vô tình bỏ hostname/purpose checks.

### 3.4. Default SSLContext và JVM system properties

Khi không cài custom context, JSSE có thể dùng truststore/JDK default configuration (ví dụ `cacerts`, property `javax.net.ssl.trustStore` và truststore password/type, provider chính sách). **Đừng giả định mọi JVM/container có cùng tập root CA**: JDK distribution, image, hệ điều hành và enterprise policies có thể khác.

Lệnh minh họa cấu hình **truststore riêng cho process Java**:

```shell
java -Djavax.net.ssl.trustStore=truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -Djavax.net.ssl.trustStorePassword=changeit YourApp
```

Lệnh chỉ có tác dụng nếu class `YourApp` tồn tại, dùng JSSE default trust managers tương ứng và chạy trong thư mục có file. Đây **không phải lab chính**; lab chính truyền `SSLContext` rõ ràng. Tránh đặt password thật trên command line hoặc config công khai.

**Quan trọng:** một code path đã tạo `SSLContext` với custom `TrustManagerFactory` và truyền nó vào client **không nhất thiết bị override** bởi JVM `javax.net.ssl.trustStore`. Phân biệt **default context của JVM** với **explicit context per client** khi debug.

---

## 4. Hostname verification là một phép kiểm danh tính riêng

Certificate của `api.example.com` thường có:

```text
Subject: CN=Example API
Subject Alternative Name:
  DNS:api.example.com
  DNS:orders.example.com
Issuer: Trusted CA / Intermediate CA
Public key: ...
```

Giả sử certificate đó có chain hợp lệ tới CA trong truststore. Khi client gọi `https://admin.example.com`, chain vẫn có thể hợp lệ nhưng **hostname không khớp SAN**. Một HTTPS client an toàn **phải từ chối**.

### 4.1. Hai điều kiện AND, không phải OR

```text
            Server certificate
                │
        ┌───────┴───────────┐
        ▼                   ▼
  PKIX trust path      Endpoint identity
  / trusted CA         / hostname or IP SAN
        │                   │
        └───────── AND ─────┘
                     │
               Peer accepted
             (subject to other
               TLS policies)
```

`Certificate chain valid` chỉ giúp trả lời “certificate đã được một chuỗi issuer hợp lệ từ trust anchor chấp thuận cấp”. `Hostname valid` trả lời “certificate có dùng được cho **tên đích mà ứng dụng yêu cầu** không?”. Hai bên không nên thỏa hiệp.

Trong HTTPS hiện đại, kiểm tên dựa trên **SAN**, không “lấy CN substring cho khớp”. Nếu URL dùng IP literal, cần SAN loại **iPAddress**, không coi `DNS:127.0.0.1` là tương đương. Với Unicode domain/IDNA, wildcard và nhiều loại identifiers, **dùng endpoint identity implementation chuẩn** thay vì `String.contains`/regex tự chế.

### 4.2. `HostnameVerifier` của `HttpsURLConnection`

`HttpsURLConnection` có:

```java
HttpsURLConnection connection = (HttpsURLConnection) url.openConnection();
connection.setSSLSocketFactory(sslContext.getSocketFactory());
// Không gọi setHostnameVerifier(...) khi dùng verification chuẩn.
```

Đây là minh họa, biến `url` và `sslContext` phải được tạo trước. **Giữ verifier mặc định** cho HTTPS trừ khi bạn thực sự đang triển khai một chính sách identity thay thế đã được kiểm chứng; việc cung cấp custom verifier rất dễ làm hostname validation sai.

Một số API có `setDefaultHostnameVerifier(...)` ở phạm vi default toàn JVM/handler, có thể ảnh hưởng các kết nối tạo sau đó. Không coi thao tác global như lựa chọn “chỉ thay một request”. Tránh phụ thuộc hành vi global mutable defaults trong service đa luồng hoặc nhiều tenant.

#### Anti-pattern cực kỳ nguy hiểm

```java
// SAI: bypass hostname verification!
connection.setHostnameVerifier((hostname, session) -> true);
```

Kẻ tấn công có thể cung cấp chứng thư hợp lệ cho **tên khác**, hoặc kết hợp cấu hình trust quá rộng để MITM. Nếu gặp hostname mismatch, hãy sửa URL/certificate SAN hoặc PKI issuance; **không** đổi verifier thành always-true.

### 4.3. `HttpClient` không có `setHostnameVerifier` công khai

`java.net.http.HttpClient` cho phép:

```java
HttpClient client = HttpClient.newBuilder()
        .sslContext(sslContext)
        .build();
```

Đây là minh họa, cần `import java.net.http.HttpClient;` và biến `sslContext`. Trong cách dùng chuẩn, HTTP client thực hiện HTTPS endpoint identification trong quá trình TLS theo chính sách của implementation. **Không có `HttpClient.Builder.hostnameVerifier(...)`** để áp callback tương tự `HttpsURLConnection.setHostnameVerifier`.

`HttpClient.Builder.sslParameters(SSLParameters)` có thể điều chỉnh các tham số TLS được hỗ trợ; không phải hook hostname verifier dành riêng cho một URL. Các tham số không được implementation cho phép có thể bị bỏ qua, phụ thuộc JDK/provider. **Không dựa vào `sslParameters` hay internal JVM flags để vô hiệu hóa kiểm hostname**.

Cũng không nên dùng property nội bộ dạng `jdk.internal.httpclient.disableHostnameVerification` để sửa lỗi. Đây không phải thiết kế bảo mật hoặc public API ổn định; việc tắt endpoint identity gây rủi ro MITM.

### 4.4. Raw `SSLSocket` lại là câu chuyện khác

Nếu tự dùng `SSLSocket` thay vì HTTP client:

```java
SSLSocket socket = (SSLSocket)
        sslContext.getSocketFactory().createSocket("api.example.com", 443);
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
```

Đây **không phải chương trình độc lập**. Đừng mặc định raw `SSLSocket` tự kiểm tên URL khi ứng dụng chưa chỉ định algorithm; raw socket API không biết HTTP host semantics ở cùng mức như HTTP client. Khi dùng `HttpClient`/`HttpsURLConnection`, hãy **giữ** cơ chế hostname verification chuẩn của chính client.

---

## 5. Cấu hình `HttpsURLConnection`: scope cụ thể và lỗi global defaults

Quy trình sử dụng phổ biến:

1. Tạo `URL` bắt đầu bằng `https://`.
2. Tạo `HttpsURLConnection` từ `url.openConnection()`.
3. Trước khi kết nối, gọi `connection.setSSLSocketFactory(sslContext.getSocketFactory())`.
4. Đặt timeout, HTTP headers/verb cần thiết.
5. Đọc `getResponseCode()` và response/error streams đúng, sau đó đóng.
6. Gọi `disconnect()` khi không cần connection nữa; lưu ý underlying HTTP keep-alive có quy tắc pooling của handler.

```java
HttpsURLConnection connection =
        (HttpsURLConnection) new URL("https://api.example.com").openConnection();
connection.setSSLSocketFactory(sslContext.getSocketFactory());
connection.setConnectTimeout(5000);
connection.setReadTimeout(5000);
try {
    int status = connection.getResponseCode();
    // Đọc đúng input/error stream và xử lý status.
} finally {
    connection.disconnect();
}
```

Đây là **đoạn minh họa chưa độc lập**, cần imports, `sslContext` và exception handling. **Không gắn một `HostnameVerifier` không kiểm chứng**.

### 5.1. Phạm vi instance so với default global

| Cách gọi | Phạm vi ý nghĩa |
| --- | --- |
| `connection.setSSLSocketFactory(factory)` | Factory cho đối tượng `HttpsURLConnection` này, trước lúc connect |
| `connection.setHostnameVerifier(verifier)` | Policy callback hostname cho instance này; không dùng để bypass |
| `HttpsURLConnection.setDefaultSSLSocketFactory(factory)` | Thay default factory cho các instance về sau theo hành vi API; ảnh hưởng các phần khác JVM |
| `HttpsURLConnection.setDefaultHostnameVerifier(verifier)` | Thay default verifier cho các instance về sau; có thể phá identity checking trên diện rộng |
| `SSLContext.setDefault(context)` | Đổi default SSLContext JVM; không coi là thiết lập riêng một URL |

Trong ứng dụng web nhiều threads/tenants/libraries, **không đổi global defaults khi xử lý một request**. Thread khác có thể mở kết nối trong lúc defaults đã bị đổi; các clients tạo trước đó có thể còn giữ factory cũ. Chọn **per-connection factory** hoặc client được xây riêng cho trust domain.

### 5.2. Giới hạn và đặc điểm legacy API

- Response code/status, input vs error stream cần xử lý rõ; `getInputStream` có thể ném exception cho HTTP error statuses.
- Timeouts/caching/redirects và keep-alive do `HttpURLConnection`/handler quản lý. Đừng coi một instance như một client immutable dùng song song vô hạn.
- Không làm IO/blocking lâu trong event-loop quan trọng.
- Mỗi lần gọi `openConnection` là một đối tượng connection mới; underlying network connection có thể được reuse theo policy, vì vậy không tự suy luận một handshake mới cho mỗi HTTP request.
- Khi redirect từ host A sang B, phải đánh giá security policy: credentials/authorization headers, host allowlist và TLS identity của **host đích**; truststore không tự kiểm rủi ro SSRF/open redirect.

---

## 6. Cấu hình `HttpClient`: client reusable, TLS context theo client

Trong Java 17, cách sử dụng hiện đại:

```java
HttpClient client = HttpClient.newBuilder()
        .sslContext(customSslContext)
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NEVER)
        .version(HttpClient.Version.HTTP_1_1)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/orders"))
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();

HttpResponse<String> response =
        client.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

Đây là **đoạn minh họa chưa độc lập**: imports `java.net.http.*`, `java.net.URI`, `java.time.Duration`, `java.nio.charset.StandardCharsets`, biến `customSslContext` và exception handling cần được cung cấp. Bản chạy hoàn chỉnh nằm ở mục 8.

### 6.1. Vì sao nên reuse `HttpClient`?

`HttpClient` được thiết kế để sử dụng qua nhiều requests: quản lý kết nối, HTTP/2 streams, threads và TLS sessions nội bộ. Tạo một `HttpClient` mới cho mỗi HTTP request có thể làm mất cơ hội reuse và tăng chi phí handshake/connection setup. **Nhưng reuse phải theo trust domain**: nếu tenant A dùng CA riêng, không nên bỏ CA đó vào một client tin tất cả tenants chỉ để tái sử dụng.

Một thiết kế service:

```text
ClientRegistry
 ├─ publicApiClient   : default/public trust policy
 ├─ internalApiClient : enterprise CA truststore
 └─ partnerClient     : partner CA + client identity (mTLS)

Each client:
  SSLContext fixed when built
  connection pool and HTTP protocol policy
  URL/host allowlist + request authorization policy
```

Dùng URL trong `HttpRequest` quyết định endpoint. `HttpClient` được build với một `SSLContext` cụ thể; muốn thay truststore/certificate rotation, tạo client/context mới theo cơ chế có kiểm soát và migrate/close các session liên quan theo lifecycle của JDK/framework. Không giả định sửa file `truststore.p12` trên disk làm các HttpClient đang chạy lập tức dùng key/trust anchors mới.

### 6.2. `sslParameters(...)` dùng để làm gì?

`HttpClient.Builder.sslParameters(SSLParameters)` cho phép đặt một tập SSL/TLS parameters, ví dụ protocols/cipher suites theo policy nếu provider/implementation chấp nhận. Tuy nhiên, theo Java API, **một số tham số có thể không được phép hoặc bị bỏ qua** trong ngữ cảnh HttpClient.

Đừng viết một `SSLParameters` với endpoint identification rỗng để “không kiểm hostname”. Khi cần hostname verification khác chuẩn (như workload URI identity), hãy chọn giao thức/HTTP stack và lớp kiểm chứng identity được hỗ trợ, thay vì bypass TLS rồi tự so chuỗi một cách thiếu an toàn.

### 6.3. Redirect, async và proxy là trách nhiệm khác TLS trust

- Mặc định `HttpClient.Redirect.NEVER`; nếu cho phép redirect, yêu cầu có thể đi tới host khác, và **URL mới phải được đánh giá** theo policy/allowlist. Một SSLContext tin nhiều CA không tự ngăn bị chuyển tới endpoint ngoài dự kiến.
- `sendAsync` trả `CompletableFuture`; exception có thể được wrap trong `CompletionException`; không nuốt lỗi TLS rồi coi request thành công.
- Proxy có thể dùng `ProxySelector`; nếu proxy chấm dứt TLS (gateway/SSL inspection), chứng thư mà JSSE quan sát có thể do CA doanh nghiệp cấp. Chỉ tin CA đó khi policy tổ chức có căn cứ; **không tắt kiểm certificate** chỉ vì bị proxy.
- HTTP/2/ALPN không thay nhiệm vụ xác minh certificate chain và tên endpoint.
- Đọc body stream/response đúng hạn mức; `HttpClient` có resource lifecycle và body handler khác với legacy `getInputStream`.

### 6.4. `HttpClient.sslContext()` chỉ cho biết context, không phải identity đã được kiểm

`client.sslContext()` trả về cấu hình context sử dụng bởi client. Một `SSLContext` object có thể được tạo với trust-all manager sai. **Không kiểm chứng bảo mật bằng cách chỉ assert client.sslContext()!=null**. Cần integration test với CA không trusted, host không khớp SAN, cert hết hạn và policy clientAuth phù hợp.

---

## 7. Cùng một truststore nhưng kết quả vẫn có thể khác

Giả sử hai HTTP clients cùng dùng `sslContext` tin root CA nội bộ. Vì sao kết quả vẫn khác nhau?

| Khác biệt | Ví dụ | Cách kiểm |
| --- | --- | --- |
| URL/hostname | Legacy gọi `localhost`, modern gọi `127.0.0.1` | SAN DNS vs SAN iPAddress |
| Proxy | Một client dùng proxy doanh nghiệp, client kia direct | Chứng thư nhìn thấy ở TLS endpoint, proxy policy |
| Redirect | Một client follow redirect sang host khác | Host mới, credentials transfer, trust policy |
| TLS protocols/ciphers | Một bên ép TLS 1.3, bên kia provider chọn TLS 1.2 | Enabled protocols, JSSE debug |
| Client identity | Một context có `KeyManager`, context kia không | mTLS `CertificateRequest`, alias, EKU |
| Trust anchors | Client mới được build sau rotation, client cũ giữ context trước | Keystore reload/rebuild, truststore inventory |
| Connection pool | Reused connection/session vs full handshake mới | TLS session identity, resumption và log |
| Hostname policy | Legacy custom `HostnameVerifier`, modern default strict | Loại bỏ unsafe override; kiểm SAN và endpoint |
| HTTP version | HTTP/1.1 vs HTTP/2, ALPN | Request format/network behavior, **không phải lý do tắt TLS** |
| JVM configuration | System properties, security providers hoặc internal flags khác | Effective runtime, process configuration, build/deployment |

**Thứ tự debug hợp lý:** kiểm URL/port/SAN → trust chain/root → key usage/EKU → SSLContext & key managers → TLS protocol/proxy → HTTP redirect/body. Đừng đổi cả trust manager và hostname verifier cùng lúc; khi đó bạn không còn biết lỗi thật từ đâu.

---

## 8. Lab Java 17+: HTTPS server cục bộ + hai HTTP clients

Lab sử dụng **training root CA** ký chứng thư `localhost`, rồi hai clients cùng tin root qua **`truststore.p12`**. Cả hai truy cập **một HTTPS endpoint thực** trong JVM, giữ hostname checking chuẩn của JDK.

**Tài sản:**

- `ca.p12`: chứa private key của training CA, **không đưa vào ứng dụng client**.
- `ca.pem`: public root CA certificate.
- `server.p12`: server private key + leaf certificate `DNS:localhost` + chain.
- `truststore.p12`: **chỉ chứa public CA certificate được tin**, không có private key.
- `HttpsClientsLab.java`: bắt đầu HTTPS server cục bộ, chạy `HttpsURLConnection` và `HttpClient` với cùng `SSLContext` cho client.

**Bảo mật lab:** mật khẩu `changeit` và private CA key chỉ phục vụ học; không dùng production. Chạy trong **thư mục lab trống**, không ghi đè keystore thật, không thêm root demo vào `cacerts` hệ thống. Lệnh để password trên command-line chỉ dành cho lab; production không để password lộ qua shell history/process list.

### 8.1. Sinh root CA giả lập

```shell
keytool -genkeypair -alias training-ca -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=HTTPS Lab Root CA, O=Training, C=VN" -validity 3650 -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -keystore ca.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
```

Export CA certificate công khai:

```shell
keytool -exportcert -alias training-ca -keystore ca.p12 -storepass changeit -file ca.pem -rfc
```

**Không dùng CA certificate chính nó để làm server certificate.** Trong lab này root ký trực tiếp leaf (path length không có intermediate). Một hệ thống thực có thể dùng intermediate CA, HSM và issuance policy cụ thể.

### 8.2. Tạo server private key và CSR cho `localhost`

```shell
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost, O=Training, C=VN" -validity 365 -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
keytool -certreq -alias localhost -keystore server.p12 -storepass changeit -file localhost.csr -ext "SAN=dns:localhost"
```

CSR xin chứng thư gắn public key của server với `localhost`, nhưng **chưa phải certificate tin cậy**; CA sẽ cấp leaf theo policy.

### 8.3. Root ký server leaf với SAN và EKU chính xác

```shell
keytool -gencert -alias training-ca -keystore ca.p12 -storepass changeit -infile localhost.csr -outfile server.pem -rfc -validity 30 -ext "SAN=dns:localhost" -ext "KU:critical=digitalSignature" -ext "EKU=serverAuth" -ext "BC=ca:false"
```

Import CA rồi certificate reply vào server keystore, bảo đảm private-key entry có chain:

```shell
keytool -importcert -alias training-ca -file ca.pem -keystore server.p12 -storepass changeit -noprompt
keytool -importcert -alias localhost -file server.pem -keystore server.p12 -storepass changeit -noprompt
```

`server.p12` giữ **server private key**; `server.pem` chỉ là bản chứng thư công khai, không bao gồm khóa riêng.

### 8.4. Client tin root trong truststore riêng

```shell
keytool -importcert -alias training-ca -file ca.pem -keystore truststore.p12 -storetype PKCS12 -storepass changeit -noprompt
```

Đây là **trust decision** của client trong lab. Không nhập root này vào truststore toàn JVM của hệ thống. Nếu dùng root lạ từ kênh không xác thực, attacker có thể khiến client tin chứng thư giả.

Kiểm các trường mục đích trước khi chạy:

```shell
keytool -printcert -file server.pem
keytool -list -v -keystore server.p12 -storetype PKCS12 -storepass changeit
keytool -list -v -keystore truststore.p12 -storetype PKCS12 -storepass changeit
```

Chờ thấy `SAN=dns:localhost`, `ExtendedKeyUsage=serverAuth`, server `PrivateKeyEntry` và root `trustedCertEntry`; serial, fingerprints và timestamps thay đổi, **không có stdout cố định cho keytool**.

### 8.5. Chương trình Java hoàn chỉnh

Tạo file **`HttpsClientsLab.java`** trong cùng thư mục với hai file `server.p12` và `truststore.p12`:

```java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.Duration;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class HttpsClientsLab {
    private static final char[] LAB_PASSWORD =
            "changeit".toCharArray(); // DEMO ONLY

    private static KeyStore load(String path) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(path))) {
            store.load(in, LAB_PASSWORD);
        }
        return store;
    }

    private static SSLContext context(String ownKeyStore)
            throws Exception {
        KeyManager[] keys = null; // HTTPS client one-way: no client cert.
        if (ownKeyStore != null) {
            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(load(ownKeyStore), LAB_PASSWORD);
            keys = kmf.getKeyManagers();
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(load("truststore.p12")); // Explicit trusted CA(s).

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keys, tmf.getTrustManagers(),
                new SecureRandom());
        return context;
    }

    private static String legacyGet(String endpoint,
            SSLContext tlsContext) throws Exception {
        HttpsURLConnection connection = (HttpsURLConnection)
                new URL(endpoint).openConnection();
        connection.setSSLSocketFactory(
                tlsContext.getSocketFactory());
        // No unsafe custom HostnameVerifier: HTTPS name checked normally.
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(5000);
        try {
            int status = connection.getResponseCode();
            if (status != 200) {
                throw new IllegalStateException(
                        "Legacy HTTP status: " + status);
            }
            try (InputStream in = connection.getInputStream()) {
                return new String(in.readAllBytes(),
                        StandardCharsets.UTF_8).trim();
            }
        } finally {
            connection.disconnect();
        }
    }

    private static String modernGet(String endpoint,
            SSLContext tlsContext) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .sslContext(tlsContext)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(endpoint))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Modern HTTP status: " + response.statusCode());
        }
        return response.body().trim();
    }

    public static void main(String[] args) throws Exception {
        SSLContext serverContext = context("server.p12");
        SSLContext clientContext = context(null);

        HttpsServer server = HttpsServer.create(
                new InetSocketAddress("localhost", 0), 0);
        server.setHttpsConfigurator(
                new HttpsConfigurator(serverContext));
        server.createContext("/hello", exchange -> {
            byte[] body = "OK\n".getBytes(StandardCharsets.UTF_8);
            try {
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream output =
                        exchange.getResponseBody()) {
                    output.write(body);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();
            String endpoint =
                    "https://localhost:" + port + "/hello";
            String legacy = legacyGet(endpoint, clientContext);
            String modern = modernGet(endpoint, clientContext);

            System.out.println("legacyBody=" + legacy);
            System.out.println("modernBody=" + modern);
            System.out.println(
                    "bothReadSamePayload=" + legacy.equals(modern));
            System.out.println(
                    "separateKeyAndTrustManagers=true");
        } finally {
            server.stop(0);
        }
    }
}
```

**Tại sao đây là ví dụ đúng ranh giới?**

- HTTPS server có **server private key** từ `server.p12` qua `KeyManagerFactory`.
- Cả hai HTTP clients có **truststore chứa CA** qua `TrustManagerFactory`, không có private-key identity (vì one-way HTTPS).
- `HttpsURLConnection` cài context bằng `setSSLSocketFactory` trên **instance**, không đổi global default; giữ hostname verifier mặc định.
- `HttpClient` nhận `sslContext` ở **builder**, không có custom verifier; cả hai gọi URL `https://localhost:port/hello` khớp `SAN DNS:localhost`.
- Server listen cổng tự động (port `0`) để tránh xung đột với dịch vụ đang chạy; chỉ truy cập endpoint cục bộ trong lab.
- Cả hai request được đọc qua JSSE HTTPS channel; chương trình **không tự thực hiện thủ công TLS handshake hoặc AES**.
- Chỉ in các giá trị application-level cố định, **không in private keys, truststore password, certificate fingerprint hay session secrets**.

### 8.6. Biên dịch và chạy Java 17+

Module `jdk.httpserver` chứa `com.sun.net.httpserver.HttpsServer` và `HttpsConfigurator`. Dùng cờ explicit để module được resolve cả khi biên dịch và chạy:

```shell
javac --add-modules jdk.httpserver HttpsClientsLab.java
java --add-modules jdk.httpserver HttpsClientsLab
```

**Stdout kỳ vọng** khi đã tạo keystore/truststore từ bước 8.1–8.4, chạy trong thư mục lab với một JDK 17 thông dụng hỗ trợ RSA/PKCS12/JSSE:

```text
legacyBody=OK
modernBody=OK
bothReadSamePayload=true
separateKeyAndTrustManagers=true
```

Giá trị serial/fingerprint và TLS session keys ngẫu nhiên không được in, vì vậy stdout của chương trình không phụ thuộc chúng. Nếu không tìm thấy `server.p12`, `truststore.p12`, sai password, thiếu private key/chain hoặc root không tin cậy, chương trình **không** in đủ kết quả trên mà báo exception; đó là một kiểm tra bảo mật hữu ích, không phải lý do tắt TLS.

### 8.7. Điều gì lab cố ý chưa minh họa?

- Đây là HTTPS server học tập chạy cục bộ, **không phải production web server**. Không có auth/token, IAM, quota, rate limiting, request validation, nhiều handlers, monitoring, revocation/OCSP infrastructure, certificate rotation, HSM/KMS.
- Chưa có client certificate/mTLS. Để làm mTLS cần bổ sung **client private key/certificate chain** và cấu hình server yêu cầu client certificate, truststore cho client CA; không chỉ gọi `setNeedClientAuth(true)` mà không cài keystore/trust managers.
- Chương trình không có negative tests làm thay đổi hostname: default behavior được giữ, còn thử negative test có hướng dẫn ở mục 9.
- `HttpsServer` dùng default TLS parameters từ `HttpsConfigurator`. Production cần kiểm protocol/cipher suites, key/certificate lifecycle và resource controls theo policy.
- Cấu hình một truststore root CA riêng trong lab có nghĩa **không mặc định tin toàn bộ public Web PKI**; đây là scope có chủ ý.

---

## 9. Các bài thử thất bại để xác thực ranh giới

Chỉ chạy trên **bộ certificate/truststore của lab**, không sửa truststore production hoặc hệ thống. Kiểm outcome và exception type/chuỗi chứng thư thực tế, **không so khớp toàn bộ exception message** vì thay đổi theo JDK/provider/OS.

### 9.1. Test 1 – Certificate chain không được tin

Tạo `untrusted.p12` không chứa `training-ca` hoặc CA ký server leaf. Tạo một `SSLContext` mới từ store đó rồi dùng cho từng API. Kết nối sẽ bị từ chối nếu peer không thể xây đường tin cậy đến trust anchor; lỗi thường có `SSLHandshakeException`, `PKIX path building failed` hoặc `unable to find valid certification path`.

**Không chữa bằng trust-all:** cần nhập đúng root CA đã được phê duyệt vào truststore theo kênh đáng tin và giữ certificate chain hợp lệ.

### 9.2. Test 2 – Hostname không khớp SAN

Server certificate chỉ có `SAN DNS:localhost`. Nếu server vẫn có thể được kết nối tại `127.0.0.1` nhưng request URL là `https://127.0.0.1:port/hello`, HTTPS endpoint identification phải kiểm SAN loại `iPAddress` và từ chối khi certificate **không** có `IP:127.0.0.1`.

**Chú ý:** môi trường có thể bind `localhost` tới IPv6 `::1`, IPv4 `127.0.0.1` hoặc hosts settings khác; nếu không thể connect qua IP literal thì đó là **lỗi kết nối**, không chứng minh đã chạy hostname check. Để test chắc chắn, cấu hình test server listen đúng interface và certificate SAN/connection rõ, sau đó kiểm exception liên quan tên.

Không giải quyết bằng `connection.setHostnameVerifier((h,s) -> true)`. Với client cần gọi bằng IP literal, certificate phải có IP SAN đúng, hoặc dùng DNS hostname được chứng thực.

### 9.3. Test 3 – Đổi server certificate nhưng giữ root CA đáng tin

Tạo leaf mới do **cùng root CA** ký, nhưng SAN chỉ chứa `DNS:other.example`. Chain vẫn có thể hợp lệ tới trust anchor, nhưng request `https://localhost` **phải bị từ chối** do identity mismatch.

Bài test này chứng minh **truststore tin CA không phải danh sách những host tự động được chấp nhận**. Một CA có thể cấp nhiều certificates cho nhiều names; client kiểm đúng name cho từng URL.

### 9.4. Test 4 – Client mTLS thiếu private key

Nếu server yêu cầu `clientAuth`, chỉ nhập public client certificate vào client truststore không làm client có khả năng chứng minh sở hữu private key. Client phải có **`PrivateKeyEntry` với cert chain** trong keystore, `KeyManagerFactory` nạp entry phù hợp và server phải tin client CA. Không dùng `clientAuth` cert làm serverAuth tùy tiện.

### 9.5. Test 5 – Mối nguy global defaults

Một JVM có service A tin CA đối tác A và service B tin CA đối tác B. Nếu service A gọi `HttpsURLConnection.setDefaultSSLSocketFactory(factoryA)` ở startup hoặc trong một request, những kết nối khác tạo sau đó có thể vô tình dùng trust configuration A.

**Thiết kế đúng:** tạo `SSLContext` theo trust domain, dùng `setSSLSocketFactory` cho từng legacy connection hoặc `HttpClient.Builder.sslContext` cho reusable client. Cấu hình global chỉ nên áp dụng khi **toàn process thật sự có cùng policy** và được quản lý như deployment config.

---

## 10. mTLS trên cả hai APIs: cấu hình nào thay đổi?

Trong **one-way HTTPS**, client cần trust manager để xác minh server, nhưng không bắt buộc có client private key. Trong **mTLS**, client phải có private key/certificate chain, server phải yêu cầu chứng thư và xác thực client.

Tương tự một phương thức khởi tạo context trong lab:

```java
SSLContext clientTls = context("client.p12");
```

Đây **chỉ là đoạn minh họa**: `client.p12` phải tồn tại, có `PrivateKeyEntry` đúng EKU `clientAuth` và CA của server phải được tin ở truststore. `context(...)` trong lab cũng khởi tạo `TrustManagerFactory` để **client tiếp tục kiểm server**. Bản thân dòng này **không ép server yêu cầu clientAuth**; server phải được cấu hình tương ứng.

### 10.1. `HttpsURLConnection` với mTLS

```java
connection.setSSLSocketFactory(clientTls.getSocketFactory());
```

Đây là phần cài đặt **identity/trust context** trên legacy connection. Khi server gửi `CertificateRequest` trong handshake, JSSE key manager chọn client certificate phù hợp để trình bày. Không nhầm client keystore với truststore server.

### 10.2. `HttpClient` với mTLS

```java
HttpClient mtlsClient = HttpClient.newBuilder()
        .sslContext(clientTls)
        .build();
```

Đây là phần cài đặt context ở builder. mTLS hoạt động nếu server thực sự yêu cầu và hai phía có key/certificate/trust chains đúng policy. Không có `HttpClient.Builder.clientCertificate(...)` chuẩn để thay thế toàn bộ `KeyManagerFactory` trong một bước đơn giản.

### 10.3. Chọn client certificate không chỉ là “có file”

Nếu keystore có nhiều aliases/certificates, `X509KeyManager`/`X509ExtendedKeyManager` có thể chọn dựa trên key type, CA hints, signature algorithms, TLS version và provider. Một alias có `clientAuth` sai, private key không khớp chain hoặc identity chưa được server chấp thuận sẽ làm handshake thất bại. Tùy framework/JDK, có thể cần policy chọn alias được kiểm soát; **không bỏ trust/hostname validation để sửa lỗi chọn key**.

### 10.4. mTLS và authorization

Dù client certificate được server xác thực thành công, server vẫn phải map identity (SAN URI, DNS, Subject DN theo CA policy) thành principal rồi kiểm **role, tenant, object và action**. Có client certificate không tự có quyền `admin`. Nếu mTLS kết thúc ở proxy/service mesh, ứng dụng phải tin đúng nguồn của forwarded principal, chặn client tự gửi header mạo danh.

---

## 11. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Vùng nguyên nhân | Việc cần làm |
| --- | --- | --- |
| `PKIX path building failed` | Truststore thiếu root, chain thiếu intermediate, CA không được phép | Kiểm trust anchors và chain ở **phía client**; nhập qua kênh có thẩm quyền |
| `No subject alternative names matching IP address` | URL dùng IP nhưng cert chỉ có DNS SAN | Cấp IP SAN đúng hoặc dùng DNS hostname được chứng nhận |
| `No name matching ... found` | DNS SAN không khớp URL hostname | Kiểm URL/SAN/certificate issuance, không tắt hostname verifier |
| `certificate_unknown`/`bad_certificate` | Peer không chấp nhận cert/chain/purpose | Kiểm issuer, EKU, KU, validity, protocol và trust managers |
| `certificate_required`/`Empty client certificate chain` | Server yêu cầu mTLS nhưng client không có identity key | Nạp client keystore vào KeyManagerFactory, kiểm chain/alias |
| `handshake_failure` | TLS versions/cipher/signature incompatibility hoặc authentication | Kiểm effective protocols, certificate/key types và JSSE debug |
| `UnrecoverableKeyException` | Keystore/entry password sai hoặc private key không truy xuất | Kiểm keystore path, alias, provider và secret source |
| `FileNotFoundException` | Store file không nằm trong process working directory | Dùng path explicit và kiểm deployment filesystem |
| HTTPS trả `401`/`403` sau handshake | Ứng dụng không chấp nhận token/role/tenant | Kiểm application auth, không sửa TLS một cách mù quáng |
| Legacy thành công, modern `PKIX` fail | Hai client dùng SSLContext/truststores khác, proxy khác, hoặc cert khác | Ghi context source, URL và truststore policy; đừng suy luận cùng JVM ⇒ cùng trust |
| Legacy thành công, modern báo sai hostname | Legacy có unsafe HostnameVerifier custom hoặc URL khác | Khôi phục hostname verification chuẩn, kiểm certificate SAN |
| Một HttpClient gọi nhiều domains; cần CA riêng từng domain | Trust scope quá rộng hoặc thiếu cấu hình | Dùng clients riêng theo trust domain / policy |
| Sau CA rotation vẫn dùng chứng thư cũ | Context/client đã build trước, connections có session reuse | Rebuild/reload có kiểm soát và cập nhật trust store |
| Hệ thống hoạt động khi tắt validation | Config hoặc certificate thực tế sai; test che rủi ro MITM | Không đưa bypass vào production; sửa nguyên nhân gốc |
| Client tự theo redirect đến host ngoài allowlist | Redirect policy/SSRF/credential forwarding | Disable hoặc kiểm redirect destinations, secrets và host policy |
| Proxy chuyển TLS certificate | TLS termination/enterprise inspection | Xác định chính sách proxy/CA được tổ chức chấp thuận |

### 11.1. Debug JSSE có kiểm soát

Có thể bật debug trong môi trường lab:

```shell
java -Djavax.net.debug=ssl,handshake,trustmanager --add-modules jdk.httpserver HttpsClientsLab
```

Lệnh tạo nhiều debug lines về handshake, trust manager và certificate chain; stdout/stderr **không cố định** theo JDK/provider. **Không bật debug nhạy cảm dài hạn ở production**, không đưa private key, token, plaintext hoặc dữ liệu định danh ngoài phạm vi audit vào logs.

Một checklist debug thực tế:

1. Ghi chính xác URL/hostname/port mà mỗi API đang sử dụng.
2. Xác định có proxy/redirect/TLS termination nào thay endpoint thật.
3. Kiểm server leaf `SAN`, time validity, EKU `serverAuth` và intermediates.
4. Xác định trust manager đã load **root CA nào**, từ default store hay custom store.
5. Kiểm client identity `KeyManager` khi mTLS.
6. Kiểm provider/JDK TLS version/cipher suites, `jdk.tls.disabledAlgorithms`, TLS session reuse.
7. Nếu certificate trusted nhưng host sai, **sửa host/SAN**, không đổi trust manager.
8. Nếu host đúng nhưng chain không trusted, **sửa truststore/chain**, không đổi hostname verifier.

### 11.2. Chữ ký chứng thư đúng chưa đủ

Có thể gọi `cert.verify(issuerPublicKey)` thành công nhưng server vẫn bị từ chối vì:

- issuer public key không phải trusted CA;
- path constraints, key usage hoặc critical extensions không hợp lệ;
- cert hết hạn hoặc bị revoke;
- SAN hostname không khớp URL;
- peer không chứng minh sở hữu private key qua handshake;
- thuật toán TLS/certificate bị policy cấm.

**Đừng sửa bằng cách tự kiểm issuer signature rồi bỏ qua JSSE/HTTPS validation.** Cần duy trì toàn chuỗi kiểm tra theo protocol.

---

## 12. Các ranh giới vượt khỏi `SSLContext`

### 12.1. Certificate pinning

**Pinning** ràng buộc một certificate/public key/SPKI hoặc tập khóa được chấp thuận cho một service để giảm phạm vi tin cậy. Nhưng pinning **không được coi là lý do bỏ CA/hostname validation tùy tiện**. Phải có kế hoạch rotation, backup pins, pin set update và cơ chế recovery hợp lý để không tự khóa hệ thống khi certificate thay đổi.

`HttpClient` không có một public `HostnameVerifier` callback như legacy. Nếu tổ chức muốn pinning, ưu tiên thư viện/provider/HTTP stack hoặc custom trust logic được đánh giá đầy đủ; cần giữ **trust, identity, lifecycle** thay vì chỉ so fingerprint hay tắt hostname. Pinning thường dành cho threat model cụ thể, không nên ép tất cả APIs.

### 12.2. TLS client certificates và network identity

Một `SSLContext` với `KeyManagers` có thể cung cấp client certificate khi server yêu cầu, nhưng **không quyết định authorization**. Từ phía server, TLS xác thực principal theo PKI; ứng dụng còn phải kiểm permissions cho resource. Nếu client dùng certificate của tenant A để gọi API tenant B, authorization phải từ chối kể cả certificate chain hợp lệ.

### 12.3. SNI, IP literal và virtual hosts

Client muốn gọi `https://example.com` có thể gửi SNI `example.com`, server chọn certificate tương ứng; client vẫn kiểm SAN tên `example.com`. Nếu client kết nối một IP literal, certificate cần IP SAN tương ứng. **SNI không phải bằng chứng CA trust hoặc hostname match**; nó là input cho server virtual hosting/routing.

Không dùng một custom `SSLSocketFactory` để chuyển traffic đến IP nội bộ tùy tiện nhưng báo hostname khác, nếu không hiểu endpoint identity được JSSE sử dụng. Với reverse proxy, cần phân biệt URL host, TLS server name, Host/:authority HTTP header, certificate SAN và backend route.

### 12.4. Redirects và SSRF: trust đúng vẫn có thể gọi sai host

Một request HTTPS đến host tin cậy có thể trả `302` sang host khác. Nếu HTTP client tự theo redirect, thông tin/authorization headers, cookies hoặc data flow có thể bị ảnh hưởng. Client phải có allowlist/redirect policy, không chỉ dựa vào “TLS certificate của host đích cũng hợp lệ”. SSRF là lỗi chọn destination; certificate validation **không phải** bộ lọc host an toàn.

### 12.5. Khi làm việc qua proxy

Một HTTP proxy có thể chuyển CONNECT tunnel mà không giải mã TLS; một enterprise inspection proxy có thể **terminate/re-sign** TLS bằng CA doanh nghiệp. Client sẽ xác minh certificate mà nó **thực sự nhìn thấy**, theo trust policy của JVM/context. Không được import một CA không rõ nguồn hoặc tắt TLS verification chỉ vì kết nối qua proxy.

### 12.6. Runtime JDK và cập nhật chính sách thuật toán

Các JDK cập nhật danh sách disabled algorithms, TLS protocol defaults, root CA bundles và behavior của provider. Một cấu hình từng hoạt động có thể bị từ chối khi thuật toán/certificate yếu không còn chấp nhận. Giải pháp là nâng key/certificate và policy theo tài liệu, **không hạ mức `jdk.tls.disabledAlgorithms` tùy tiện** chỉ để pass test.

---

## 13. Câu hỏi tự kiểm tra và đáp án

**1. `SSLContext` có trực tiếp chứa URL hostname không?**  
Không. URL/request cung cấp endpoint; SSLContext cung cấp TLS key/trust infrastructure. HTTPS client/JSSE áp dụng endpoint identification phù hợp khi handshake.

**2. Tại sao certificate do CA đáng tin ký vẫn có thể bị HTTPS từ chối?**  
Vì hostname không khớp SAN, expired/revoked, EKU/KU/path constraints hoặc thuật toán không hợp lệ. “CA trusted” chỉ là một phần điều kiện.

**3. Cách gắn SSLContext riêng lên `HttpsURLConnection`?**  
Dùng `connection.setSSLSocketFactory(context.getSocketFactory())` **trước khi connect**, giữ hostname verifier chuẩn.

**4. Cách gắn SSLContext riêng lên Java 17 `HttpClient`?**  
Dùng `HttpClient.newBuilder().sslContext(context).build()`, tái sử dụng client cho trust domain tương ứng.

**5. `HttpClient.Builder` có `hostnameVerifier(...)` giống legacy không?**  
Không. Không nên dùng internal JVM flags hoặc `SSLParameters` để bypass HTTPS endpoint verification.

**6. Khi nào client cần `KeyManagerFactory`?**  
Khi HTTP client phải trình bày private-key identity, điển hình mTLS. One-way TLS thường cần trust manager, không cần client certificate.

**7. `tmf.init(internalStore)` có đương nhiên tin cả public Web PKI không?**  
Không. Trust scope phụ thuộc store/provider; một store chỉ có internal root thường chỉ tin root đó. Nếu phải tin các domain khác nhau, thiết kế clients/truststores theo policy.

**8. Vì sao không dùng `setHostnameVerifier((h,s)->true)`?**  
Nó từ bỏ kiểm endpoint identity và tạo nguy cơ chấp nhận certificate cho tên khác, tăng rủi ro MITM.

**9. Tại sao không thay `HttpsURLConnection.setDefaultSSLSocketFactory` theo từng request?**  
Đây là global default cho các kết nối mới trong JVM; gây ảnh hưởng ngoài phạm vi request và race condition với threads/clients khác.

**10. Hai client đều có SSLContext cùng truststore; tại sao một vẫn fail?**  
Có thể URL host khác, proxy/redirect khác, key managers/cert selection khác, TLS version/provider hoặc hostname verifier legacy bị custom sai. Cần so context **và** endpoint policy.

**11. Root CA mới được thêm vào truststore trên disk; HttpClient đã build có tự tin CA mới không?**  
Không nên giả định. Phải có cơ chế reload/rebuild SSLContext/HttpClient và xử lý connection/session lifecycle.

**12. Chỉ kiểm `X509Certificate.verify(caKey)` có thay HTTPS validation được không?**  
Không. Nó không tự kiểm trust anchor, PKIX path, hostname, revocation, proof-of-possession và TLS handshake integrity.

**13. Certificate `SAN DNS:localhost` có hợp lệ khi URL là `https://127.0.0.1` không?**  
Không theo kiểm IP identity chuẩn nếu thiếu SAN `iPAddress:127.0.0.1`. Tránh nhầm kết nối socket thành công với hostname verification hợp lệ.

**14. mTLS có làm client tự có quyền truy cập toàn bộ API không?**  
Không. TLS xác thực principal; IAM/ACL/tenant permissions là tầng ứng dụng.

**15. Có nên tạo `HttpClient` mới cho mọi request không?**  
Thông thường không; tái sử dụng để quản lý connection pooling và chi phí TLS, nhưng tách client theo trust domain/policy.

**16. Có cách nào chạy HTTPS khi chứng thư partner sai mà không bật trust-all?**  
Sửa nguyên nhân: cấp đúng certificate SAN/EKU, gửi đủ intermediates, dùng truststore chứa CA được phê duyệt và URL chính xác. Không dùng bảo mật giả cho production.

---

## 14. Checklist triển khai Java HTTPS an toàn

- [ ] **Chọn client API**: legacy nếu tích hợp code cũ, modern `HttpClient` khi cần reusable/async/HTTP2; biết rõ scope TLS configuration.
- [ ] **Đúng URL**: host/port/path/scheme và redirect policy; chống SSRF và credential leakage.
- [ ] **Trust anchors**: CA/cert đưa vào truststore từ nguồn đáng tin; không trust-all hoặc import CA không rõ nguồn.
- [ ] **Server certificate**: chain, validity, SAN, EKU `serverAuth`, KU/purpose, thuật toán/key size theo policy.
- [ ] **Hostname verification**: giữ HTTPS endpoint identity checking; không dùng verifier luôn true hoặc undocumented disable flags.
- [ ] **Scope**: `setSSLSocketFactory` trên instance legacy, `sslContext` trên builder modern; tránh mutation global defaults khi có nhiều clients.
- [ ] **mTLS**: nếu cần, có client `PrivateKeyEntry` + chain + KeyManagerFactory, server có trusted client CA và `needClientAuth`.
- [ ] **AuthZ**: mapping certificate identity → service principal → tenant/role/operation checks, tách khỏi TLS trust.
- [ ] **Lifecycle**: CA/root, leaf và private key có rotate/revoke/reload strategy; connection pool/resumption và long-lived sessions có chính sách.
- [ ] **Timeout/resource**: connect/read/request timeouts, HTTP status/error stream, body size, redirect và proxy controls.
- [ ] **Observability**: có log mức vừa đủ cho TLS handshake failure và certificate chain, không dump private key/password/plaintext.
- [ ] **Negative tests**: CA không tin, SAN sai host/IP, cert expired, EKU sai, thiếu intermediates, mTLS thiếu client key, redirect khác host, misconfigured proxy.
- [ ] **Production QA**: test trên đúng JDK/provider/container image và cấu hình JSSE thực tế; không lấy “demo pass” làm bằng chứng toàn bộ security policy.

**Kết luận cần nhớ:** `SSLContext` quản lý **nguồn key/trust và phần TLS engine**; **HTTPS endpoint identification** cần gắn certificate với **hostname đang gọi**. `HttpsURLConnection` cho phép cài `SSLSocketFactory` theo từng connection và có `HostnameVerifier` dễ bị lạm dụng. `HttpClient` nhận `SSLContext` ở builder và không cung cấp public hostname-verifier callback tương đương. **Sửa sai CA/hostname bằng trust-all hoặc tắt verifier là phá an ninh, không phải cấu hình đúng.**

## 15. Tài liệu tham khảo chính thống

- [Java SE 17 – HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): `setSSLSocketFactory`, `setHostnameVerifier`, các default factories/verifiers.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): reusable HTTP/1.1/HTTP2 client, SSLContext, request/response, async và client lifecycle.
- [Java SE 17 – HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `sslContext`, `sslParameters`, `connectTimeout`, `followRedirects` và `proxy`.
- [Java SE 17 – SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html), [KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html) và [TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo TLS context từ identity và peer trust.
- [Java SE 17 – SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification/protocol/cipher parameters.
- [Java SE 17 – HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html) và [HttpsConfigurator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html): triển khai local HTTPS server cho lab.
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, truststore/keystore, PKIX, `SSLSocket` và debugging.
- [JDK 17 keytool manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): key pair, CSR, CA signing, import cert reply, PKCS12.
- [RFC 5280 – X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate path validation, CA constraints và SAN.
- [RFC 9525 – Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): HTTPS/TLS endpoint identity checks.
- [RFC 8446 – TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake và server authentication.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): cấu hình TLS an toàn và các anti-pattern cần tránh.