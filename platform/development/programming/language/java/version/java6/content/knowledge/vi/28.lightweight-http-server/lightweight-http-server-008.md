# HTTP server gọn: HttpsServer, HttpsConfigurator và SSLContext

## Mục tiêu và phạm vi

**`HttpsServer`** là biến thể của `HttpServer` hỗ trợ HTTPS qua TLS, thuộc **module `jdk.httpserver`** do JDK cung cấp. Muốn triển khai HTTPS, không thể chỉ đổi URL từ `http://` sang `https://`: server phải có **private key + X.509 certificate**, xây dựng **`SSLContext`**, gắn **`HttpsConfigurator`** rồi dùng **`SSLParameters`** để áp chính sách TLS. Phía client phải **tin đúng certificate chain và kiểm tra hostname/IP SAN**. Khi cần client cũng xuất trình certificate, đó là **mutual TLS (mTLS)**.

Bài tập trung vào đúng ba đối tượng:

1. **`HttpsServer`:** TLS listener và HTTP contexts, executor, request handler, start/stop.
2. **`HttpsConfigurator`:** liên kết SSLContext với HTTPS server, cấu hình SSLParameters cho mỗi HTTPS connection.
3. **`SSLContext`:** JSSE context khởi tạo bằng **KeyManager[]** (identity), **TrustManager[]** (xác minh peer) và SecureRandom.

Sau bài học, bạn có thể nạp PKCS12 keystore, xây server/client SSLContext, tự tạo certificate tạm bằng `keytool` có SAN chính xác, cấu hình TLSv1.3/TLSv1.2 bằng `SSLParameters.setProtocols`, phân biệt one-way TLS và mTLS, lấy negotiated `SSLSession` từ `HttpsExchange` và kiểm tra các tình huống fail-handshake mà không cần tắt security verification.

**Special Note:** Chỉ sử dụng kiến thức còn áp dụng hiện nay. Các setters `HttpsParameters.setProtocols`, `setCipherSuites`, `setNeedClientAuth` và `setWantClientAuth` **đã deprecated từ JDK 23**: cấu hình thay thế phải dùng **`SSLParameters`**, rồi truyền vào `HttpsParameters.setSSLParameters(ssl)`. Không khuyên dùng trust-all, bỏ hostname verification, SSLv3/TLSv1.0/TLSv1.1, thuật toán yếu hay chứng chỉ demo trong production. Mã hoàn chỉnh dùng Java 17+, được biên dịch với `javac --release 17` và chạy thực tế trên OpenJDK 24.

## 1. HTTPS có thêm TLS, còn HTTP handler vẫn là HTTP

```text
          Client HttpClient                         JDK HttpsServer
                |                                         |
                +----------- TLS handshake ------------->|
                |<------ certificate + negotiation ------|
                |                                         |
                +------- encrypted HTTP request -------->|
                |         method, URI, headers, body      +--> HttpHandler
                |                                         |
                |<------ encrypted HTTP response --------+
                |         status, headers, body          |
```

Sơ đồ diễn giải khái niệm, không mô tả thứ tự cụ thể các handshake messages của TLS 1.2/1.3. Client phải xác minh server certificate trước khi tin kênh TLS. Dữ liệu HTTP được giải mã khi đến handler, vì vậy TLS **không thay thế** body validation, authorization, query/path validation, rate limits hoặc bảo vệ secrets tại storage/logs.

| TLS có thể bảo vệ | TLS không tự bảo vệ |
| --- | --- |
| Bảo mật truyền tải trên một TLS connection | DB, logs, queue và memory đã giải mã |
| Server identity nếu certificate chain và SAN được client xác minh | Danh tính user cuối nếu chưa có application auth |
| Client identity khi bật mTLS | Quyền truy cập business cho mọi endpoint |
| Chọn TLS protocol/cipher suite | DoS bằng body lớn, HTTP routing bugs |
| Integrity trên kênh | Data bị thay đổi sau TLS termination |

Khi kết nối đi qua gateway/reverse proxy, TLS có thể terminate ở proxy; hop proxy→backend **không tự được mã hóa**. Xác định trust boundary từng hop, không tin tùy tiện `Host`/`X-Forwarded-*` của client.

## 2. Các classes và modules còn hiệu lực

| Java API | Module | Vai trò |
| --- | --- | --- |
| `com.sun.net.httpserver.HttpsServer` | `jdk.httpserver` | HTTPS listener, contexts, lifecycle |
| `com.sun.net.httpserver.HttpsConfigurator` | `jdk.httpserver` | SSLContext và TLS connection settings |
| `com.sun.net.httpserver.HttpsParameters` | `jdk.httpserver` | Nhận SSLParameters qua `setSSLParameters` |
| `com.sun.net.httpserver.HttpsExchange` | `jdk.httpserver` | `HttpExchange` có `getSSLSession` |
| `javax.net.ssl.SSLContext` | `java.base` | Context TLS với key/trust managers |
| `javax.net.ssl.SSLParameters` | `java.base` | Protocols, cipher suites, client authentication |
| `javax.net.ssl.SSLSession` | `java.base` | Negotiated protocol/cipher, certificate principals |
| `java.security.KeyStore` | `java.base` | Identity private key entries / trusted certs |
| `KeyManagerFactory` | `java.base` | Private key + certificate chain để chứng minh identity |
| `TrustManagerFactory` | `java.base` | Trust anchors và xác minh peer certificate |
| `java.net.http.HttpClient` | `java.net.http` | HTTPS client dùng trong integration fixture |

`jdk.httpserver` là **JDK-specific public module**, không phải internal `sun.*`. Nó có trong JDK 26, nhưng một runtime image tạo bởi `jlink` có thể không bao gồm nó nếu không yêu cầu. Trong ứng dụng named module dùng cả server và test client:

```java
module demo.https {
    requires jdk.httpserver;
    requires java.net.http;
}
```

Đây là snippet của `module-info.java`, tách khỏi file classpath runnable phía dưới. Không cần `--add-exports` để dùng các public `com.sun.net.httpserver` APIs.

## 3. Server identity, trust và certificate

### Server phải có private key

Server cần `PrivateKeyEntry` gồm private key và certificate/certificate chain. Dùng `KeyStore.getInstance("PKCS12")` (kiểu chuẩn bắt buộc của Java SE 26) thay vì suy đoán file legacy JKS. `KeyManagerFactory` đọc private-key entry và cung cấp keys cho SSLContext:

```text
server.p12  --load--> KeyStore
                        |
                        +--> KeyManagerFactory.init(keys, password)
                                    |
                                    v
                                KeyManager[]
                                    |
                                    v
                            SSLContext.init(...)
```

**Không** gửi `server.p12` chứa private key cho client. Không commit credentials, không đặt password thực trong source.

### Client chỉ cần tin server certificate (HTTPS một chiều)

Client dùng `TrustManagerFactory` init từ trusted certificates/CA roots. Với self-signed certificate chỉ để test, client có thể tạo truststore trong bộ nhớ và **pin đúng certificate thử nghiệm**. Không tạo custom `X509TrustManager` với `checkServerTrusted()` rỗng.

### mTLS đòi hai chiều

| HTTPS server-authenticated | mTLS |
| --- | --- |
| Server có KeyManagers/server cert | Server có KeyManagers/server cert |
| Client có TrustManagers để xác minh server | Client có TrustManagers để xác minh server |
| Client không buộc có keypair | Client có KeyManagers/client private key + cert |
| Server không cần kiểm tra client cert | Server có TrustManagers để xác minh client chain |
| `ssl.setNeedClientAuth(false)` | `ssl.setNeedClientAuth(true)` |
| HTTP/app auth cần làm riêng | HTTP/app authorization **vẫn** cần làm riêng |

**Chứng chỉ client hợp lệ không tự biến thành quyền business.** Hãy map subject/SAN/CA/workload identity tới principal, rồi áp chính sách authorization.

### SAN và EKU

Certificate server dùng cho `https://127.0.0.1` phải có `IP SAN=127.0.0.1`. Tên `CN=localhost` **không thay** hostname/IP verification dựa trên SAN. Đối với demo, server cert có `EKU=serverAuth`, client cert có `EKU=clientAuth`. Khi production dùng CA thật, cần quản lý issuer/chain/expiry/revocation theo PKI policy.

## 4. Tạo hai certificates chỉ để kiểm thử bằng keytool

Công cụ `keytool` nằm trong JDK. Mỗi test dùng **thư mục tạm mới** chứa `server.p12` và `client.p12`, validity 2 ngày, RSA-2048 và SHA256withRSA. Password sau đây là **giả lập**; command-line `-storepass` có thể bị ghi nhận trong process list, **không áp dụng cho secrets production**.

### Windows PowerShell

```powershell
$env:TLS_DEMO_PASSWORD = "demo-only-308-not-for-production"

keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 2 -storetype PKCS12 -keystore server.p12 -storepass $env:TLS_DEMO_PASSWORD -keypass $env:TLS_DEMO_PASSWORD -dname "CN=localhost, OU=Test, O=Demo, L=HCMC, ST=HCMC, C=VN" -ext "SAN=ip:127.0.0.1,dns:localhost" -ext "EKU=serverAuth" -noprompt

keytool -genkeypair -alias client -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 2 -storetype PKCS12 -keystore client.p12 -storepass $env:TLS_DEMO_PASSWORD -keypass $env:TLS_DEMO_PASSWORD -dname "CN=demo-client, OU=Test, O=Demo, L=HCMC, ST=HCMC, C=VN" -ext "EKU=clientAuth" -noprompt

javac --release 17 HttpsServerTlsDemo.java
java HttpsServerTlsDemo server.p12 client.p12
```

### POSIX shell (Linux/macOS)

```bash
export TLS_DEMO_PASSWORD='demo-only-308-not-for-production'

keytool -genkeypair -alias server \
 -keyalg RSA -keysize 2048 -sigalg SHA256withRSA \
 -validity 2 -storetype PKCS12 -keystore server.p12 \
 -storepass "$TLS_DEMO_PASSWORD" -keypass "$TLS_DEMO_PASSWORD" \
 -dname "CN=localhost, OU=Test, O=Demo, L=HCMC, ST=HCMC, C=VN" \
 -ext "SAN=ip:127.0.0.1,dns:localhost" -ext "EKU=serverAuth" -noprompt

keytool -genkeypair -alias client \
 -keyalg RSA -keysize 2048 -sigalg SHA256withRSA \
 -validity 2 -storetype PKCS12 -keystore client.p12 \
 -storepass "$TLS_DEMO_PASSWORD" -keypass "$TLS_DEMO_PASSWORD" \
 -dname "CN=demo-client, OU=Test, O=Demo, L=HCMC, ST=HCMC, C=VN" \
 -ext "EKU=clientAuth" -noprompt

javac --release 17 HttpsServerTlsDemo.java
java HttpsServerTlsDemo server.p12 client.p12
```

Đặt file Java trong cùng thư mục test với hai keystores. Nếu file đích đã tồn tại, **không overwrite keystore thật**; dùng thư mục khác. Sau test, xóa đúng hai files vừa tạo, unset `TLS_DEMO_PASSWORD` và không commit thư mục test. Trên Windows PowerShell khi đúng thư mục test:

```powershell
Remove-Item -LiteralPath server.p12, client.p12 -Force
Remove-Item Env:TLS_DEMO_PASSWORD
```

Chỉ xóa khi chắc chắn `server.p12`/`client.p12` là fixtures tạm do bạn tạo, không phải keys của service.

## 5. Xây SSLContext cho server

```java
KeyStore serverKeys = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(serverKeyPath)) {
    serverKeys.load(input, password);
}
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(serverKeys, password);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(kmf.getKeyManagers(), null, new SecureRandom());
```

Đây là **snippet tích hợp**, yêu cầu `Path serverKeyPath` và `char[] password` cùng imports. `SSLContext.getInstance("TLS")` mới chỉ tạo JSSE context, **chưa nạp private key**. `SSLContext.init(...)` nhận danh sách key managers chứa server identity. Với HTTPS một chiều, server không yêu cầu client cert, nên chưa cần TrustManagers riêng cho client identity.

`SSLContext.getDefault()` có thể phục vụ client system trust, nhưng **không được giả định** chứa đúng server certificate/private key của ứng dụng. Với server, hãy init explicit key material từ PKCS12 hoặc HSM/secret-manager integration.

### TLS versions

Theo Java SE 26, TLS 1.2 và 1.3 là những `SSLContext` protocols bắt buộc được hỗ trợ. Sử dụng `SSLContext.getInstance("TLS")` cho TLS family rồi đặt `SSLParameters` phù hợp. Đừng dùng `SSLContext.getInstance("SSL")` làm lựa chọn security mới, đừng cố bật các giao thức TLS cũ hoặc ciphers yếu đã bị `jdk.tls.disabledAlgorithms` vô hiệu hóa.

## 6. HttpsConfigurator sử dụng SSLParameters hiện đại

`HttpsServer` yêu cầu một `HttpsConfigurator`. Javadoc mô tả `configure(HttpsParameters)` chạy khi **HTTPS connection** được thiết lập, không phải method chuyên xử lý từng HTTP request.

```java
server.setHttpsConfigurator(new HttpsConfigurator(sslContext) {
    @Override
    public void configure(HttpsParameters params) {
        SSLParameters ssl = getSSLContext().getDefaultSSLParameters();
        ssl.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
        ssl.setNeedClientAuth(false);
        params.setSSLParameters(ssl);
    }
});
```

Đây là snippet có `HttpsServer server`, `SSLContext sslContext` đã init. `getDefaultSSLParameters()` trả bản sao các cấu hình TLS mặc định của context/provider. Code thay protocols và client-auth policy có chủ đích, giữ tập cipher suites mặc định đã qua các JSSE security properties.

**Tránh API deprecated:** từ JDK 23, `HttpsParameters.setProtocols`, `setCipherSuites`, `setNeedClientAuth`, `setWantClientAuth` được khuyến nghị thay bằng `SSLParameters.setProtocols`/`setCipherSuites`/`setNeedClientAuth`/`setWantClientAuth`, sau đó gọi `params.setSSLParameters(ssl)`. Code demo **không** gọi các deprecated methods đó.

### Cấu hình theo kết nối, không theo request

Một TCP/TLS connection có thể mang nhiều HTTP requests nhờ keep-alive. Vì thế nếu dùng `AtomicInteger configured` đếm số callbacks, con số **không bằng số requests** một cách chắc chắn. Hãy đo traffic ở HTTP handler/metrics layer, không suy luận request count từ TLS callback count.

### setNeedClientAuth và setWantClientAuth

- `ssl.setNeedClientAuth(false)`: không bắt buộc client cert.
- `ssl.setWantClientAuth(true)`: yêu cầu tùy chọn, client thiếu cert **có thể vẫn kết nối**.
- `ssl.setNeedClientAuth(true)`: bắt buộc client cert, handshake phải fail nếu không có chứng chỉ hợp lệ.

Hai flags có semantics loại trừ nhau; gọi một method có thể reset trạng thái kia theo Javadoc. Với mTLS bắt buộc, dùng **need=true** và đúng server TrustManager.

### Cipher suites

`SSLParameters.setCipherSuites(...)` có thể áp allowlist theo policy, nhưng không copy danh sách cipher cũ. TLS 1.2 và TLS 1.3 có suites khác nhau; provider, certificate algorithms và `jdk.tls.disabledAlgorithms` còn giới hạn kết quả. Fixture **không hardcode một suite cụ thể**, chỉ kiểm tra `SSLSession.getCipherSuite()` không rỗng sau handshake.

## 7. HttpsServer bind, handler, executor và stop

```java
HttpsServer server = HttpsServer.create(
    new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
server.setHttpsConfigurator(new HttpsConfigurator(sslContext));
server.createContext("/secure", exchange -> {
    try (exchange) {
        // Xử lý request và gửi response.
    }
});
ExecutorService executor = Executors.newFixedThreadPool(3);
server.setExecutor(executor);
server.start();
```

Đây là **skeleton** chưa có `finally` dừng server và executor; file hoàn chỉnh ở mục 10 có cleanup. `setExecutor` phải gọi trước `start`. Port `0` yêu cầu OS chọn ephemeral port; `getAddress().getPort()` cho port thật. Bind `127.0.0.1` giúp tránh expose test server cho Internet.

`createContext` dùng prefix path matching, **không tự làm routing/authorization**. Một context `"/secure"` có thể match thêm URI bắt đầu cùng prefix; nếu business chỉ cho phép đúng một path, handler phải kiểm tra. HTTP exchange vẫn cung cấp `getRequestMethod`, `getRequestURI`, `getRequestHeaders`, `getRequestBody`, `sendResponseHeaders` và `getResponseBody`.

`server.stop(0)` và `executor.shutdownNow()` trong fixture phục vụ test ngắn; production cần graceful shutdown, timeout và thread-pool capacity policy. HTTPS không tự giới hạn body size, header count hay slow uploads.

## 8. SSLSession trong HTTPS handler và client

`HttpsExchange` mở rộng `HttpExchange`:

```java
HttpsExchange https = (HttpsExchange) exchange;
SSLSession session = https.getSSLSession();
String tlsProtocol = session.getProtocol();
String negotiatedCipher = session.getCipherSuite();
```

Đây là snippet bên trong HTTPS handler. `tlsProtocol` có thể là `TLSv1.3` hoặc `TLSv1.2`, **không** phải HTTP version. Với một HTTPS response, client `HttpResponse.sslSession()` có thể trả `Optional<SSLSession>` để kiểm tra tương tự.

### Khi server không có client certificate

Trong HTTPS một chiều, `getSSLSession().getPeerPrincipal()` phía server có thể ném `SSLPeerUnverifiedException`, vì **server không yêu cầu client certificate**. Điều đó không đồng nghĩa HTTPS server certificate verification ở phía client thất bại.

Trong mTLS, server có thể lấy verified client `Principal` rồi **map qua identity/role policy**. Đừng coi `CN=demo-client` tự cấp quyền admin hay quyền truy cập tài khoản bất kỳ.

## 9. HTTPS client đúng cách: TrustManager và hostname verification

Với server self-signed certificate test, client tạo truststore trong memory, chỉ chứa **đúng cert**:

```java
KeyStore trust = KeyStore.getInstance("PKCS12");
trust.load(null, null);
trust.setCertificateEntry("trusted-demo-server", serverCertificate);
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext clientTls = SSLContext.getInstance("TLS");
clientTls.init(null, tmf.getTrustManagers(), new SecureRandom());

HttpClient client = HttpClient.newBuilder()
        .sslContext(clientTls)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
```

Đây là snippet, cần `Certificate serverCertificate` từ fixture và imports. Không dùng custom trust-all `X509TrustManager`. Mặc định `HttpClient` thực hiện HTTPS endpoint identity checking; chứng chỉ thử có SAN IP 127.0.0.1, phù hợp URL `https://127.0.0.1`.

### Default client bị từ chối là kết quả đúng

`HttpClient.newHttpClient()` dùng default trust anchors. Một self-signed certificate mới sinh trong test **không có trong truststore mặc định**, vì thế handshake thường thất bại. Không “sửa” bằng cách tắt certificate/hostname verification; phải cung cấp trust anchor hợp lệ.

### Trust chain và hostname là hai điều kiện

Ngay cả khi TrustManager tin certificate, URL hostname/IP phải khớp chứng chỉ SAN. Không dùng `jdk.internal.httpclient.disableHostnameVerification` hoặc `HttpsURLConnection.setDefaultHostnameVerifier` để bỏ qua. Nếu cần kết nối domain thật, có certificate và SAN đúng domain, không tái sử dụng demo localhost cert.

## 10. Chương trình Java 17+ hoàn chỉnh, đã chạy thực tế

**File:** `HttpsServerTlsDemo.java`. Trước tiên dùng `keytool` tạo `server.p12` và `client.p12` theo mục 4, đặt `TLS_DEMO_PASSWORD`. Chương trình mở hai HTTPS servers (mỗi server chỉ bind loopback). Tests gửi requests bằng `java.net.http.HttpClient` chứ không mock TLS. Một server không đòi client cert, server kia cấu hình mTLS với TrustManager chỉ tin cert thử nghiệm của client. Không có trust-all hoặc hostname bypass.

### 10.1. Source code

```java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsExchange;
import com.sun.net.httpserver.HttpsParameters;
import com.sun.net.httpserver.HttpsServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.Certificate;
import java.time.Duration;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLPeerUnverifiedException;
import javax.net.ssl.TrustManagerFactory;

public final class HttpsServerTlsDemo {
    private static final String TEXT = "Bảo mật TLS 🌏 & Java";

    private static KeyStore loadKeys(Path file, char[] password) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(file)) {
            ks.load(input, password);
        }
        return ks;
    }

    private static KeyManagerFactory keyManagers(KeyStore store, char[] password)
            throws Exception {
        KeyManagerFactory factory = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        factory.init(store, password);
        return factory;
    }

    private static TrustManagerFactory trustThisCertificate(Certificate cert)
            throws Exception {
        KeyStore trust = KeyStore.getInstance("PKCS12");
        trust.load(null, null);
        trust.setCertificateEntry("trusted-demo-certificate", cert);
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(trust);
        return factory;
    }

    private static SSLContext serverContext(KeyStore identity, char[] password,
                                             Certificate clientCertificate)
            throws Exception {
        KeyManagerFactory kmf = keyManagers(identity, password);
        SSLContext context = SSLContext.getInstance("TLS");
        if (clientCertificate == null) {
            context.init(kmf.getKeyManagers(), null, new SecureRandom());
        } else {
            TrustManagerFactory tmf = trustThisCertificate(clientCertificate);
            context.init(kmf.getKeyManagers(), tmf.getTrustManagers(),
                    new SecureRandom());
        }
        return context;
    }

    private static SSLContext clientContext(Certificate serverCertificate,
                                             KeyStore clientIdentity,
                                             char[] password) throws Exception {
        TrustManagerFactory tmf = trustThisCertificate(serverCertificate);
        KeyManagerFactory kmf = clientIdentity == null ? null
                : keyManagers(clientIdentity, password);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf == null ? null : kmf.getKeyManagers(),
                tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    private static void respond(HttpExchange exchange, String text)
            throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        Headers headers = exchange.getResponseHeaders();
        headers.set("Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, body.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(body);
        }
    }

    private static final class ServerFixture {
        final HttpsServer server;
        final ExecutorService executor;
        final AtomicInteger configured = new AtomicInteger();
        final SSLContext context;

        ServerFixture(SSLContext context, boolean needClientCertificate)
                throws IOException {
            this.context = context;
            server = HttpsServer.create(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0), 0);
            executor = Executors.newFixedThreadPool(3);
            server.setHttpsConfigurator(new HttpsConfigurator(context) {
                @Override
                public void configure(HttpsParameters params) {
                    SSLParameters ssl = getSSLContext().getDefaultSSLParameters();
                    ssl.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
                    ssl.setNeedClientAuth(needClientCertificate);
                    params.setSSLParameters(ssl);
                    configured.incrementAndGet();
                }
            });
            server.createContext("/secure", exchange -> {
                try (exchange) {
                    if (!"POST".equals(exchange.getRequestMethod())) {
                        exchange.getResponseHeaders().set("Allow", "POST");
                        byte[] response = "Method Not Allowed".getBytes(
                                StandardCharsets.UTF_8);
                        exchange.sendResponseHeaders(405, response.length);
                        try (OutputStream out = exchange.getResponseBody()) {
                            out.write(response);
                        }
                        return;
                    }
                    HttpsExchange https = (HttpsExchange) exchange;
                    String peer = "none";
                    try {
                        peer = https.getSSLSession().getPeerPrincipal().getName();
                    } catch (SSLPeerUnverifiedException expected) {
                        // One-way TLS intentionally does not identify the caller.
                    }
                    String text;
                    try (InputStream in = exchange.getRequestBody()) {
                        text = new String(in.readNBytes(1024),
                                StandardCharsets.UTF_8);
                    }
                    String reply = "method=" + exchange.getRequestMethod()
                            + "\npath=" + exchange.getRequestURI().getPath()
                            + "\nquery=" + exchange.getRequestURI().getRawQuery()
                            + "\ntrace=" + exchange.getRequestHeaders()
                                    .getFirst("X-Trace")
                            + "\nserverProtocol=" + https.getSSLSession().getProtocol()
                            + "\nclientPrincipal=" + peer
                            + "\nbody=" + text;
                    respond(exchange, reply);
                }
            });
            server.setExecutor(executor);
            server.start();
        }

        int port() {
            return server.getAddress().getPort();
        }

        void close() {
            server.stop(0);
            executor.shutdownNow();
        }
    }

    private static HttpClient client(SSLContext context) {
        return HttpClient.newBuilder()
                .sslContext(context)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    private static HttpRequest request(int port) {
        return HttpRequest.newBuilder(
                        URI.create("https://127.0.0.1:" + port
                                + "/secure?name=Java%20TLS"))
                .timeout(Duration.ofSeconds(6))
                .header("Content-Type", "text/plain; charset=UTF-8")
                .header("X-Trace", "demo")
                .POST(HttpRequest.BodyPublishers.ofString(
                        TEXT, StandardCharsets.UTF_8))
                .build();
    }

    private static HttpResponse<String> send(HttpClient client, HttpRequest req)
            throws Exception {
        return client.send(req, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
    }

    private static boolean modernProtocol(String s) {
        return "TLSv1.3".equals(s) || "TLSv1.2".equals(s);
    }

    private static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java HttpsServerTlsDemo server.p12 client.p12");
        }
        String secret = System.getenv("TLS_DEMO_PASSWORD");
        if (secret == null || secret.isEmpty()) {
            throw new IllegalStateException("Set test-only TLS_DEMO_PASSWORD");
        }
        char[] password = secret.toCharArray();
        try {
            KeyStore serverKeys = loadKeys(Path.of(args[0]), password);
            KeyStore clientKeys = loadKeys(Path.of(args[1]), password);
            Certificate serverCert = serverKeys.getCertificate("server");
            Certificate clientCert = clientKeys.getCertificate("client");
            check("pkcs12PrivateKeyAvailable",
                    serverKeys.isKeyEntry("server")
                    && clientKeys.isKeyEntry("client"));
            check("serverCertificateLoaded", serverCert != null);
            check("clientCertificateLoaded", clientCert != null);
            SSLContext oneWay = serverContext(serverKeys, password, null);
            SSLContext trustedClient = clientContext(serverCert, null, password);
            check("serverContextIsTls", "TLS".equals(oneWay.getProtocol()));
            check("clientContextIsTls", "TLS".equals(trustedClient.getProtocol()));

            ServerFixture server = new ServerFixture(oneWay, false);
            try {
                check("boundOnlyToLoopback",
                        server.server.getAddress().getAddress()
                                .isLoopbackAddress());
                check("ephemeralPortAssigned", server.port() > 0);
                check("httpsConfiguratorInstalled",
                        server.server.getHttpsConfigurator() != null);
                check("configuratorUsesExpectedContext",
                        server.server.getHttpsConfigurator()
                                .getSSLContext() == oneWay);
                HttpResponse<String> response =
                        send(client(trustedClient), request(server.port()));
                check("trustedHttpsStatus200", response.statusCode() == 200);
                check("httpsSslSessionPresent", response.sslSession().isPresent());
                check("negotiatedModernTlsProtocol", modernProtocol(
                        response.sslSession().orElseThrow().getProtocol()));
                check("cipherSuiteNegotiated", !response.sslSession()
                        .orElseThrow().getCipherSuite().isBlank());
                check("serverCertificatePrincipal",
                        response.sslSession().orElseThrow()
                        .getPeerPrincipal().getName().contains("CN=localhost"));
                check("methodRead", response.body().contains("method=POST\n"));
                check("pathRead", response.body().contains("path=/secure\n"));
                check("rawQueryRead",
                        response.body().contains("query=name=Java%20TLS\n"));
                check("headerRead",
                        response.body().contains("trace=demo\n"));
                check("utf8BodyRoundTrip",
                        response.body().contains("body=" + TEXT));
                check("serverSessionShowsModernTls",
                        response.body().contains("serverProtocol=TLSv1.3")
                        || response.body().contains("serverProtocol=TLSv1.2"));
                check("oneWayDoesNotAuthenticateClient",
                        response.body().contains("clientPrincipal=none\n"));
                check("configuratorCalled", server.configured.get() > 0);
                boolean defaultTrustRejected = false;
                try {
                    send(HttpClient.newHttpClient(), request(server.port()));
                } catch (IOException expected) {
                    defaultTrustRejected = true;
                }
                check("defaultTrustRejectsSelfSigned", defaultTrustRejected);

                HttpResponse<String> wrongMethod = send(client(trustedClient),
                        HttpRequest.newBuilder(URI.create(
                                "https://127.0.0.1:" + server.port()
                                        + "/secure")).GET().build());
                check("methodNotAllowed405", wrongMethod.statusCode() == 405);
                check("methodAllowHeader",
                        wrongMethod.headers().firstValue("Allow")
                                .orElse("").equals("POST"));
            } finally {
                server.close();
            }

            SSLContext mutual = serverContext(serverKeys, password, clientCert);
            SSLContext clientWithCertificate =
                    clientContext(serverCert, clientKeys, password);
            ServerFixture mtls = new ServerFixture(mutual, true);
            try {
                HttpResponse<String> authorized = send(
                        client(clientWithCertificate), request(mtls.port()));
                check("mutualTlsStatus200", authorized.statusCode() == 200);
                check("mutualTlsModernProtocol", modernProtocol(
                        authorized.sslSession().orElseThrow().getProtocol()));
                check("mutualTlsPeerVerified",
                        authorized.body().contains("clientPrincipal=CN=demo-client"));
                check("mutualTlsBodyRoundTrip",
                        authorized.body().contains("body=" + TEXT));
                check("mutualTlsConfiguratorCalled", mtls.configured.get() > 0);
                boolean noClientCertificateRejected = false;
                try {
                    send(client(trustedClient), request(mtls.port()));
                } catch (IOException expected) {
                    noClientCertificateRejected = true;
                }
                check("mutualTlsRequiresClientCertificate",
                        noClientCertificateRejected);
            } finally {
                mtls.close();
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

### 10.2. Biên dịch và chạy

```bash
javac --release 17 HttpsServerTlsDemo.java
java HttpsServerTlsDemo server.p12 client.p12
```

`TLS_DEMO_PASSWORD` phải được thiết lập theo mật khẩu test khi tạo PKCS12. `System.getenv` trả Java String không thể xóa hoàn toàn khỏi memory; việc copy sang `char[]` rồi `Arrays.fill` chỉ hạn chế một bản sao, **không thay thế secret manager production**. Nếu dùng module-info, cần `requires jdk.httpserver;` và `requires java.net.http;`.

### 10.3. Stdout chính xác đã chạy (OpenJDK 24)

```text
pkcs12PrivateKeyAvailable=true
serverCertificateLoaded=true
clientCertificateLoaded=true
serverContextIsTls=true
clientContextIsTls=true
boundOnlyToLoopback=true
ephemeralPortAssigned=true
httpsConfiguratorInstalled=true
configuratorUsesExpectedContext=true
trustedHttpsStatus200=true
httpsSslSessionPresent=true
negotiatedModernTlsProtocol=true
cipherSuiteNegotiated=true
serverCertificatePrincipal=true
methodRead=true
pathRead=true
rawQueryRead=true
headerRead=true
utf8BodyRoundTrip=true
serverSessionShowsModernTls=true
oneWayDoesNotAuthenticateClient=true
configuratorCalled=true
defaultTrustRejectsSelfSigned=true
methodNotAllowed405=true
methodAllowHeader=true
mutualTlsStatus200=true
mutualTlsModernProtocol=true
mutualTlsPeerVerified=true
mutualTlsBodyRoundTrip=true
mutualTlsConfiguratorCalled=true
mutualTlsRequiresClientCertificate=true
```

**31/31 ASSERTIONS PASS.** Method `check` chỉ in `name=true` nếu điều kiện đúng, ngược lại ném `AssertionError`. Chương trình được biên dịch với `javac --release 17` và chạy trên Windows OpenJDK 24, hai keystore fixtures được tạo tạm bằng keytool và xóa sau khi chạy. Không hardcode port ngẫu nhiên/cipher suite để tránh output phụ thuộc hệ thống.

### 10.4. Nhóm kiểm thử và ý nghĩa

| Test group | Assertions | Điều chứng minh |
| --- | --- | --- |
| Keystore | `pkcs12PrivateKeyAvailable`, `serverCertificateLoaded`, `clientCertificateLoaded` | Có PrivateKeyEntry và certificates |
| SSLContext | `serverContextIsTls`, `clientContextIsTls` | Dùng TLS context |
| Bind | `boundOnlyToLoopback`, `ephemeralPortAssigned` | Bind local, OS cấp port |
| Configurator | `httpsConfiguratorInstalled`, `configuratorUsesExpectedContext`, `configuratorCalled` | HttpsServer dùng đúng SSLContext và callback |
| HTTPS | `trustedHttpsStatus200`, `httpsSslSessionPresent` | Client trust certificate đúng kết nối thành công |
| TLS details | `negotiatedModernTlsProtocol`, `cipherSuiteNegotiated`, `serverCertificatePrincipal` | Protocol 1.2/1.3, cipher và server certificate |
| HTTP over TLS | `methodRead`, `pathRead`, `rawQueryRead`, `headerRead`, `utf8BodyRoundTrip` | Handler đọc request đúng sau handshake |
| Server session | `serverSessionShowsModernTls`, `oneWayDoesNotAuthenticateClient` | TLS version và không có client cert trong one-way |
| Trust fail | `defaultTrustRejectsSelfSigned` | Default client không tin cert tự ký test |
| HTTP status | `methodNotAllowed405`, `methodAllowHeader` | TLS success nhưng GET sai method trả 405+Allow |
| Mutual TLS | `mutualTlsStatus200`, `mutualTlsModernProtocol`, `mutualTlsPeerVerified`, `mutualTlsBodyRoundTrip`, `mutualTlsConfiguratorCalled` | Client cert được server tin, HTTPS request thành công |
| Client cert required | `mutualTlsRequiresClientCertificate` | mTLS không chấp nhận client thiếu cert |

**Giới hạn:** Tests chứng minh behavior trên JDK 24/provider fixture, không phải production security audit. Không kiểm thử public CA, CRL/OCSP, OCSP stapling, cert rotation, HTTP/2, TLS termination, load test, certificate expiry, TLS fallback hay hệ thống authZ thực. Chương trình có `in.readNBytes(1024)` cho payload nhỏ nên **không được coi là implementation hoàn chỉnh để reject body vượt hạn mức**; production phải đếm bytes, xử lý 413, timeouts và backpressure.

## 11. TLS error khác HTTP status

TLS handshake phải thành công trước khi một HTTP handler gửi response. Nếu server cert không được tin, SAN không khớp URL, cipher/protocol không tương thích hoặc mTLS thiếu client identity, client có thể gặp `SSLHandshakeException`/`IOException`; thường **không có HTTP 401/403**.

| Lỗi/triệu chứng | Lớp | Cách xử lý |
| --- | --- | --- |
| `PKIX path building failed` | Trust chain TLS | Trust đúng CA/cert chain; không trust-all |
| `No subject alternative names matching ...` | Endpoint identity | Sửa URL/SAN, không tắt hostname verification |
| `handshake_failure` | TLS | Kiểm tra cert, supported cipher/protocol, clientAuth |
| `certificate_required` | mTLS | Client có KeyManagers/client certificate, server trust |
| `401 Unauthorized` | HTTP authentication | Kiểm tra credentials/session/token |
| `403 Forbidden` | HTTP authorization | Kiểm tra principal/roles/policy |
| `405 Method Not Allowed` | HTTP routing | Kiểm tra method và Allow |
| `500 Internal Server Error` | App handler | Error handling/structured logs |

Có thể tạm dùng `-Djavax.net.debug=ssl:handshake` trong môi trường test để chẩn đoán, nhưng JSSE logs có thể chứa certificate metadata, không bật tràn lan trên production traffic. Không log private key/password, body và Authorization header của người dùng.

## 12. Triển khai production: các lưu ý bắt buộc

- **Cấp phát key/certificate:** PKCS12 trong demo là tự ký. Production cần PKI issuer, SAN đúng, EKU phù hợp, expiry/revocation/renewal và key rotation.
- **Key protection:** hạn chế quyền truy cập files, keystore password từ secret manager, HSM nếu cần. Không lưu private key trong nguồn hoặc artifacts public.
- **TLS policy:** TLS 1.2/1.3, cipher suites theo security policy và provider, không bật lại thuật toán yếu bị `jdk.tls.disabledAlgorithms` cấm.
- **Trust đúng:** Client dùng TrustManager có trust anchors hợp lệ và endpoint hostname check; server mTLS dùng đúng client CA/client identity allowlist.
- **Authorization:** mTLS certificate chỉ xác thực peer, không thay business authorization.
- **Resource limits:** body bytes, request duration, idle/timeouts, slow TLS handshakes, thread pool, max connections. TLS không ngăn DoS theo HTTP.
- **Routing:** `createContext` prefix matching, không tự authZ hoặc path security.
- **Certificate reload:** SSLContext được khởi tạo từ key material. Không suy ra sửa file `.p12` sẽ tự cập nhật TLS sessions; cần chiến lược reload/restart/edge rotation đã kiểm thử.
- **Reverse proxy:** nếu TLS terminate trước backend, cần bảo vệ cả hop từ proxy tới app và cấu hình trusted proxy headers.
- **Logging:** chỉ log protocol/cipher/status/correlation ID phù hợp; không log secrets hoặc toàn payload.
- **Shutdown:** graceful server.stop và executor shutdown theo request latency, không dùng test-only `stop(0)` cho mọi workload.
- **Runtime:** `jdk.httpserver` là lightweight JDK-specific module, không tự cung cấp OAuth/OIDC, WAF, HTTP/2 server stack, certificate automation, rate limits hoặc đầy đủ monitoring.

## 13. Troubleshooting

| Vấn đề | Nguyên nhân khả dĩ | Khắc phục |
| --- | --- | --- |
| HttpsServer khởi động nhưng HTTPS không thông | Chưa set HttpsConfigurator/SSLContext thiếu identity | Gắn configurator và KeyManager |
| Server chỉ có public certificate | Không có private key | PKCS12 PrivateKeyEntry |
| TrustManager dùng thay KeyManager | Sai nhiệm vụ | KM cho identity, TM cho trust |
| Client không trust server selfsigned | Cert không thuộc roots tin cậy | Pin cert test đúng, không bypass |
| Client trust cert nhưng SAN sai | Hostname mismatch | Cấp cert có SAN hợp lệ |
| mTLS thiếu client cert | Client không có keypair | Client KeyManagerFactory + PKCS12 |
| Server không trust client cert | Server TrustManager không có anchor | Update trusted client CA/cert |
| Dùng HttpsParameters.setNeedClientAuth | Setter deprecated | SSLParameters.setNeedClientAuth |
| Dùng TLSv1.0/TLSv1.1 | Protocol yếu bị disable | TLS1.2/1.3 |
| Ciphersuites không giao nhau | Hardcoded/unsupported algorithm policy | JSSE defaults/allowlist đã test |
| Cipher suite khác giữa JDKs | Normal negotiation | Không hardcode tên suite trong test |
| SSLSession.getProtocol bị hiểu là HTTP | Nhầm giao thức | Đọc TLS/HTTP metadata riêng |
| configure count khác request count | Connection reuse | Metric tại HttpHandler |
| HTTPS hoạt động nhưng API vẫn unauthorized | TLS khác HTTP auth | AuthN/AuthZ riêng |
| Body lớn làm server chậm | Chưa có limit | Request bytes/quota/timeout |
| Đổi PKCS12 mà cert không thay | Chưa reload SSLContext | Rotation lifecycle |
| Proxy báo HTTPS nhưng backend plaintext | TLS terminate ở edge | Mã hóa và trust từng hop |
| API được mở ra toàn Internet từ ví dụ | Bind interface sai | Loopback hoặc gateway/ACL |
| Không dừng executor | Leak threads | shutdown theo lifecycle |

## 14. Bài tập tự luyện

**Bài 1 — SAN:** Dùng `keytool -list -v -keystore server.p12 -storetype PKCS12` xem SAN. Vì sao URL `https://127.0.0.1` cần IP SAN?

**Bài 2 — Mất trust:** Tạo client truststore chỉ chứa một cert test khác. Kết nối phải bị từ chối. Không sửa bằng trust-all.

**Bài 3 — TLS 1.3 only:** Nếu runtime/client hỗ trợ, đặt `ssl.setProtocols(new String[] {"TLSv1.3"})` trong test, quan sát `SSLSession.getProtocol`. Không bật TLS yếu để làm bài.

**Bài 4 — Want vs need:** Trong fixture thử `setWantClientAuth(true)` với client không có cert; quan sát sự khác biệt so với `setNeedClientAuth(true)`.

**Bài 5 — Authentication vs authorization:** Dùng principal của certificate trong mTLS để ánh xạ identity, rồi áp allowlist đúng API resource. Không coi `CN=demo-client` tự là role.

**Bài 6 — Unicode body:** Gửi payload tiếng Việt có emoji qua HttpClient; so body sau HTTPS round-trip.

**Bài 7 — Bounded body:** Thay đoạn readNBytes(1024) ở demo bằng `MAX+1` và trả 413 khi vượt MAX; test 4095, 4096 và 4097 bytes, thêm timeout.

**Bài 8 — Key rotation:** Tạo server cert thứ hai có SAN đúng, diễn tập cập nhật truststore/SSLContext và đối chiếu client cũ/mới.

**Bài 9 — HTTP vs TLS error:** Gửi GET đến /secure sau TLS handshake thành công (405), rồi client không tin server cert (lỗi TLS không có HTTP status).

**Bài 10 — Edge TLS:** Vẽ client→gateway→backend, xác định các hop nào đã mã hóa, nơi giải mã bytes và nơi cần client/service identity.

## 15. Câu hỏi ôn tập

**1. HttpsServer thuộc module nào?** `jdk.httpserver`.

**2. SSLContext.getInstance("TLS") có private key server chưa?** Chưa, cần `init` với KeyManagers phù hợp.

**3. Vì sao không đưa private key vào truststore client?** Client chỉ cần trust certificate/CA, không được sở hữu private key server.

**4. KeyManagerFactory dùng làm gì?** Cung cấp identity key/certificate material cho TLS endpoint.

**5. TrustManagerFactory dùng làm gì?** Xác minh certificate của peer theo trust anchors.

**6. PKCS12 còn hiện hành không?** Có, kiểu keystore chuẩn được Java SE 26 hỗ trợ.

**7. API đúng để cấu hình HttpsServer TLS parameters?** `HttpsConfigurator.configure` tạo `SSLParameters` và gọi `HttpsParameters.setSSLParameters`.

**8. Vì sao không gọi HttpsParameters.setProtocols?** Deprecated từ JDK23; dùng `SSLParameters.setProtocols`.

**9. TLSv1.2 và TLSv1.3 được Java SE 26 hỗ trợ?** Có, theo SSLContext Javadoc.

**10. Tại sao SAN quan trọng?** Hostname/IP trong URL phải khớp tên trong certificate.

**11. Trust-all có phải cách xử lý selfsigned test không?** Không. Pin đúng cert test trong truststore.

**12. Server một chiều có nhất thiết biết client certificate không?** Không; `getPeerPrincipal` có thể ném `SSLPeerUnverifiedException`.

**13. mTLS cần gì ngoài HTTPS?** Client identity KeyManager và server TrustManager, `setNeedClientAuth(true)`.

**14. setWantClientAuth có bắt buộc client cert?** Không.

**15. Có thể có HTTP 401 khi TLS handshake fail không?** Thường không; handshake fail trước HTTP handler.

**16. getSSLSession().getProtocol() là HTTP version?** Không, đó là TLS protocol.

**17. HTTPS có tự chặn body lớn?** Không; cần body/connection/time/resource limits.

**18. mTLS certificate hợp lệ có thay authorization?** Không, phải map principal và kiểm tra quyền.

**19. Đổi server.p12 trên disk có auto reload SSLContext?** Không nên giả định, cần explicit rotation plan.

**20. 31/31 test pass có đủ chứng minh production-safe?** Không; bài chỉ kiểm tra các tình huống được test.

## Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — HttpsServer](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): TLS server cần HttpsConfigurator và các lifecycle APIs.
- [Oracle Java SE 26 — HttpsConfigurator](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html): configure theo connection và SSLParameters.
- [Oracle Java SE 24 — HttpsParameters](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsParameters.html): các methods deprecated từ JDK 23.
- [Oracle Java SE 26 — SSLContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLContext.html): init key/trust managers, TLS 1.2/1.3.
- [Oracle Java SE 26 — SSLParameters](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): protocols, cipher, client-auth.
- [Oracle Java SE 26 — HttpsExchange](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsExchange.html): SSLSession phía server.
- [Oracle Java SE 26 — SSLSession](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSession.html): negotiated protocol/cipher, peer principal.
- [Oracle Java SE 26 — KeyStore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html): PKCS12/PrivateKeyEntry.
- [Oracle Java SE 26 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): TLS identity.
- [Oracle Java SE 26 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): TLS trust.
- [Oracle Java SE 26 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html): TLS/hostname/certificate security.
- [Oracle Java SE 26 — Security Properties File](https://docs.oracle.com/en/java/javase/26/security/security-properties-file.html): TLS disabledAlgorithms.
- [Oracle Java SE 26 — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): Java HTTPS client.
- [Oracle Java SE 26 — HttpServer](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): contexts, executor, stop.
- [Oracle Java SE 26 — keytool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html): X.509/PKCS12 test certificates.

**Ghi nhớ:** `HttpsServer` cần **PKCS12 private key/cert → KeyManagerFactory → SSLContext.init → HttpsConfigurator → SSLParameters**. Client phải **TrustManager + hostname/SAN verification**; mTLS còn cần **server TrustManager cho client cert** và `SSLParameters.setNeedClientAuth(true)`. Không dùng deprecated setters trực tiếp trên HttpsParameters, không trust-all hoặc bỏ xác minh hostname. TLS bảo vệ kết nối chứ không thay HTTP authentication/authorization, body limits hay certificate lifecycle. Bài demo Java 17+ đã thử HTTPS một chiều và mTLS qua loopback với **31/31 assertions PASS**.
