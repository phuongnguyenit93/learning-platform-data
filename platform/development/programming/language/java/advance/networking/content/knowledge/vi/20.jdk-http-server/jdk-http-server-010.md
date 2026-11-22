# HttpsConfigurator, SSLContext và bài thử HTTPS cục bộ

## Mục tiêu bài học

Java 17 có HTTP server nhỏ gọn trong module `jdk.httpserver`, gồm `HttpServer` cho HTTP và `HttpsServer` cho HTTPS. Để chuyển một HTTP server thành HTTPS server đúng nghĩa, **không chỉ đổi URL từ `http://` sang `https://`**. Server cần một **`SSLContext` đã khởi tạo với khóa riêng và chứng chỉ của server**, sau đó cấu hình `HttpsServer` bằng **`HttpsConfigurator`**. Ở phía client, cần xác thực **chuỗi chứng chỉ và hostname** của HTTPS endpoint; với chứng chỉ tự ký dành cho bài thử cục bộ, ta tạo một **truststore riêng** thay vì tắt kiểm tra TLS.

Sau bài này, bạn sẽ:

- Phân biệt `HttpServer` và `HttpsServer`, nắm vai trò module `jdk.httpserver`.
- Hiểu tại sao `HttpsConfigurator` và `HttpsParameters` gắn TLS settings với từng **incoming HTTPS connection**, còn `HttpHandler` xử lý request HTTP **sau** khi TLS handshake thành công.
- Tạo `SSLContext` cho **server** bằng `KeyManagerFactory`/private key và cho **client** bằng `TrustManagerFactory`/trusted certificate.
- Phân biệt **keystore** chứa private key với **truststore** lưu certificate/CA được tin, cũng như `server.p12`, `server.crt` và `client-trust.p12`.
- Dùng `keytool` tạo self-signed certificate có **SAN DNS/IP** đúng endpoint trên loopback, import vào truststore dành riêng cho bài thử.
- Chạy chương trình **Java 17+ độc lập**, tạo một `HttpsServer` trên `127.0.0.1` và gọi `GET /hello` bằng `HttpClient` qua HTTPS thật, xác thực TLS đầy đủ.
- Quan sát **HTTP 200**, body, HTTP version, TLS session và lỗi `SSLHandshakeException` khi client không tin chứng chỉ.
- Hiểu cách điều chỉnh TLS protocols/cipher suites, khi nào mới dùng mTLS, cách quản lý threads, handlers, stream lifecycle, timeout và `stop()`.
- Chẩn đoán sai SAN/hostname, không có private key, sai mật khẩu, truststore sai, TLS protocol mismatch, thiếu cấu hình HttpsConfigurator và các lỗi production phổ biến.

**Phạm vi:** API `com.sun.net.httpserver` và `javax.net.ssl` của **Java 17 trở lên**. Chương trình thử nghiệm chỉ mở **loopback** và dùng credential giả; không được triển khai trực tiếp làm máy chủ HTTPS Internet-facing production.

## 1. Bức tranh tổng thể: HTTP chạy bên trong TLS

HTTP thông thường truyền request/response trực tiếp qua TCP. Với HTTPS, trước khi truyền HTTP application data, client và server thiết lập một phiên TLS:

~~~text
HttpClient                        HttpsServer (jdk.httpserver)
    │                                        │
    │ ─────── TCP connect ──────────────────►│
    │                                        │
    │ ─────── TLS ClientHello ──────────────►│
    │ ◄────── certificate + handshake ──────┤
    │          xác minh trust + SAN          │
    │ ◄─────► TLS handshake finished ◄─────►│
    │                                        │
    │ ====== GET /hello (encrypted) =======►│
    │       HttpsExchange / HttpHandler      │
    │ ◄====== 200 + body (encrypted) =======│
    │                                        │
    │            session/transport cleanup   │
~~~

Đây là **mô hình logic**, không phải bản chép từng thông điệp của TLS 1.2/1.3. TLS 1.3 có trình tự handshake và cách bảo vệ các thông điệp khác TLS 1.2; API Java `SSLContext`/`SSLEngine` xử lý chi tiết giao thức.

Điều cần phân biệt:

1. **TCP:** có kết nối đến IP/cổng hay không? Nếu firewall/chọn sai địa chỉ, chưa tới bước TLS.
2. **TLS handshake:** server có private key, certificate phù hợp và cipher/protocol chung hay không? Client có tin certificate và hostname hay không?
3. **HTTP:** chỉ khi TLS thành công, handler mới nhận method, URI, headers/body và trả status/response.
4. **Application authentication:** kể cả TLS đã thành công, một API vẫn có thể yêu cầu token/cookie hoặc trả HTTP 401/403 theo chính sách riêng.

**Lưu ý:** TLS server certificate giúp client xác thực endpoint và bảo vệ dữ liệu trên kênh, **không** tự chứng minh người dùng đã đăng nhập, request đã được ủy quyền hoặc response body chắc chắn đúng ngữ nghĩa nghiệp vụ.

## 2. Các lớp Java tham gia và trách nhiệm của chúng

| Thành phần | Module/package | Vai trò |
|---|---|---|
| `HttpServer` | `jdk.httpserver / com.sun.net.httpserver` | HTTP server không có TLS |
| `HttpsServer` | `jdk.httpserver / com.sun.net.httpserver` | HTTP server có TLS; cần `HttpsConfigurator` |
| `HttpsConfigurator` | `jdk.httpserver / com.sun.net.httpserver` | Chứa `SSLContext`, cung cấp/cấu hình TLS parameters cho incoming connection |
| `HttpsParameters` | `jdk.httpserver / com.sun.net.httpserver` | Nhận các SSL parameters cần áp dụng cho một HTTPS connection |
| `HttpsExchange` | `jdk.httpserver / com.sun.net.httpserver` | Một HTTPS request/response; có `getSSLSession()` |
| `HttpHandler` / `HttpExchange` | `jdk.httpserver` | Đọc HTTP request, viết headers/status/body |
| `SSLContext` | `java.base / javax.net.ssl` | Nền tảng tạo TLS engines/sockets, sử dụng KeyManager và TrustManager |
| `SSLParameters` | `java.base / javax.net.ssl` | Cấu hình TLS protocol, cipher suites, client auth, endpoint identification... |
| `KeyStore` | `java.base / java.security` | Container certificate, private-key entries, trusted certificates |
| `KeyManagerFactory` | `java.base / javax.net.ssl` | Lấy KeyManagers chọn private key + certificate của local endpoint |
| `TrustManagerFactory` | `java.base / javax.net.ssl` | Lấy TrustManagers quyết định certificate peer có được tin hay không |
| `HttpClient` / `HttpRequest` | `java.net.http` | Client để gửi HTTPS request và nhận HTTP response sau TLS |

**Quan trọng:** `HttpsConfigurator` không phải bản thân engine mã hóa, cũng không phải `HttpHandler`. Nó dùng `SSLContext` để cấu hình TLS cho connection; sau khi handshake, `HttpsExchange` mới chuyển request đến handler.

### Đồ thị cấu hình điển hình

~~~text
server.p12  [server private key + cert]
       │
       ▼
KeyStore → KeyManagerFactory
                    │
                    ▼
        SSLContext SERVER (TLS)
                    │
                    ▼
           HttpsConfigurator
                    │ configure(HttpsParameters)
                    ▼
                HttpsServer
                    │
                    ▼
           HttpHandler /exchange


server.crt [public certificate only]
       │ keytool -importcert
       ▼
client-trust.p12  [trusted cert]
       │
       ▼
KeyStore → TrustManagerFactory
                    │
                    ▼
        SSLContext CLIENT (TLS)
                    │
                    ▼
       HttpClient.Builder.sslContext(...)
                    │
                    ▼
    GET https://127.0.0.1:<dynamic-port>/hello
~~~

Dấu `<dynamic-port>` trong sơ đồ chỉ là ký hiệu khái niệm, **không phải tên host hợp lệ để chạy**. Chương trình lấy cổng động thực tế qua `server.getAddress().getPort()`.

## 3. Keystore, truststore, certificate và private key

**Keystore** và **truststore** thường cùng dùng định dạng `PKCS12`, nhưng khác **vai trò**:

- **Server keystore (`server.p12`):** lưu *private key* của server và certificate/chain tương ứng. Server cần private key để chứng minh identity trong TLS handshake. File này **bí mật**, không phát cho client.
- **Public certificate (`server.crt`):** certificate được export, có public key và thông tin identity/SAN; không có private key. Dùng để import vào truststore thử nghiệm.
- **Client truststore (`client-trust.p12`):** chứa trusted certificate/CA được client dùng để xác minh server. Trong bài này chỉ tin **self-signed certificate cụ thể**; nó không chứa private key của server.

Một file `.p12` tự nó **không biểu thị** server hay client, cũng không chứng minh trong đó là private key hay chỉ trusted certificate. Phải xem entry type/alias và cách code dùng:
- `KeyManagerFactory.init(keyStore, keyPassword)` lấy nguồn private key local.
- `TrustManagerFactory.init(trustStore)` lấy nguồn trust decisions khi kiểm tra peer certificate.

**Phân biệt chủ thể:**
- Server-auth HTTPS thường **server có key pair**, client **có trust anchors**.
- Client-auth mTLS thì **client cũng có key pair**, và server cần trust anchors kiểm tra client. Đó là tình huống nâng cao, không cần cho bài thử server-auth bình thường.

### Vì sao dùng PKCS12?

`PKCS12` là định dạng keystore phổ biến, Java 17 có hỗ trợ tiêu chuẩn. Dùng `KeyStore.getInstance("PKCS12")` thay vì phụ thuộc vào default keystore type trên các JVM hoặc cấu hình tổ chức khác nhau.

`KeyStore.load(input, password)` mở file và xác nhận password/integrity theo provider/format. `KeyManagerFactory.init(keys, password)` cần password để truy xuất private key entries; đặt nhầm password hoặc alias, server có thể không chọn được private key phù hợp và TLS handshake thất bại.

**Đừng dùng `server.p12` như truststore bên client chỉ vì file ấy chứa certificate.** Một private key nằm trong file server keystore; sao chép file cho client sẽ làm lộ key. Hãy **export certificate public** rồi import vào client truststore.

## 4. SAN và hostname validation: hai bước độc lập với trust

Certificate có thể có subject `CN=localhost`, nhưng client HTTPS hiện đại cần **Subject Alternative Name (SAN)** phù hợp với **tên/IP thật trong URI**.

Trong bài:
- Server bind `127.0.0.1`.
- Client gọi `https://127.0.0.1:<port>/hello`.
- Certificate có **`SAN=IP:127.0.0.1`**.
- Có thêm `SAN=DNS:localhost` để học viên so sánh DNS name với IP literal.

Sự khác biệt:

| URI client | Danh tính cần có trên certificate |
|---|---|
| `https://127.0.0.1:port/...` | IP SAN chứa `127.0.0.1` |
| `https://localhost:port/...` | DNS SAN chứa `localhost` |
| `https://api.example.org/...` | DNS SAN hợp lệ với `api.example.org` |
| `https://192.0.2.10/...` | IP SAN thích hợp nếu client dùng IP literal |

**CN không thay thế SAN một cách đáng tin trong cấu hình hiện đại.** Certificate có thể được truststore chấp nhận về mặt CA/public key nhưng vẫn thất bại hostname validation do tên/IP không khớp. Không “sửa” bằng cách tắt verification; sửa SAN hoặc dùng đúng endpoint URL.

### Trust ≠ identity ≠ authorization

TLS client thực hiện hai kiểm tra riêng:
1. **Trust/path validation:** certificate/chain có đi tới trust anchor được tin và thỏa constraints không?
2. **Endpoint identification:** certificate có đại diện cho hostname/IP kỳ vọng trong URI không?

Ngay cả khi cả hai thành công, API vẫn có thể yêu cầu `Authorization: Bearer ...` hoặc session cookie. `SSLContext` không phải nơi kiểm tra role/scope ứng dụng.

## 5. Tạo certificate tự ký và truststore bằng keytool

Thực hành trong **một thư mục riêng, tạm thời**, không commit vào Git. Mọi tên file của phần này đều thuộc thư mục đó. Cần cài **JDK 17+** có `keytool`, `javac` và `java`.

### 5.1. Tạo private key + server certificate

~~~bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -validity 2 -dname "CN=localhost" -ext "SAN=DNS:localhost,IP:127.0.0.1" -ext "EKU=serverAuth" -noprompt
~~~

Giải thích:
- `-alias server`: tên key entry được quản lý trong keystore.
- `-keyalg RSA -keysize 2048`: thuật toán/key size dành cho ví dụ; production phải áp chính sách cryptography được phê duyệt, có thể chọn EC.
- `-storetype PKCS12`: định dạng keystore.
- `-storepass` và `-keypass`: mật khẩu **giả cho bài thử**, không dùng thực tế.
- `-validity 2`: thời hạn **hai ngày**, cố tình rất ngắn.
- `-dname "CN=localhost"`: subject name.
- `-ext "SAN=DNS:localhost,IP:127.0.0.1"`: hai identity cho phép kiểm tra hostname/IP.
- `-ext "EKU=serverAuth"`: mục đích dùng key/certificate cho server-auth.

**Bảo mật:** truyền password trên command line có thể lưu trong history/log/process metadata. Ở hệ thống thật dùng secret manager, file permissions và cách cấp phát key an toàn; không dùng `changeit` và không để private key thử nghiệm trên máy chủ production.

### 5.2. Export certificate public

~~~bash
keytool -exportcert -alias server -rfc -keystore server.p12 -storepass changeit -file server.crt
~~~

`server.crt` là certificate công khai, **không chứa private key**. Kiểm tra nội dung certificate nếu cần bằng:

~~~bash
keytool -printcert -file server.crt
~~~

Hãy xác nhận extension **SubjectAlternativeName** có cả DNS `localhost` và IP `127.0.0.1`. Khi certificate expired (hai ngày sau lúc tạo), phải sinh certificate mới và cập nhật truststore; lỗi expiry không được “sửa” bằng trust-all.

### 5.3. Tạo client truststore bằng cách import public cert

~~~bash
keytool -importcert -noprompt -alias localserver -file server.crt -keystore client-trust.p12 -storetype PKCS12 -storepass changeit
~~~

Thao tác này chấp nhận **self-signed certificate cụ thể** là một trust anchor cho bài thử. Khi bạn tạo lại `server.p12` với một keypair khác, certificate mới không còn tương ứng certificate cũ trong `client-trust.p12`; phải cập nhật truststore.

### 5.4. Kiểm tra alias và entry types

~~~bash
keytool -list -v -keystore server.p12 -storetype PKCS12 -storepass changeit
keytool -list -v -keystore client-trust.p12 -storetype PKCS12 -storepass changeit
~~~

Kỳ vọng:
- `server.p12`: alias `server`, **PrivateKeyEntry** (private key + chain).
- `client-trust.p12`: alias `localserver`, **trustedCertEntry**.

**Không chia sẻ `server.p12`** với người chạy client. Trong ví dụ, server và client nằm trong cùng một JVM nên cùng process đọc hai file khác nhau; production thường tách máy/service và quản trị certificate/private key theo vai trò.

## 6. `SSLContext`: nơi hội tụ private-key identity và trust policy

Javadoc `SSLContext` mô tả nó là một đối tượng cấu hình TLS/SSL implementation, có thể tạo socket factories và `SSLEngine`. Thông thường:

~~~java
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, null);
~~~

Đây là **snippet**, giả định `keyManagers`/`trustManagers` đã được tạo; tham số cuối `null` yêu cầu nguồn `SecureRandom` mặc định. Tên `"TLS"` **không có nghĩa** “bắt buộc TLS 1.3”; protocol thực tế được negotiation theo provider/SSLParameters/client/server policy.

### 6.1. Server SSLContext

Ở server-auth HTTPS:
- `KeyManagerFactory` được khởi tạo từ `server.p12` chứa **private key**.
- `SSLContext.init(kmf.getKeyManagers(), null, null)` gắn server identity.
- Tham số TrustManagers `null` nghĩa là dùng provider default nếu cần trust decisions; vì ví dụ **không bật client authentication**, server không cần kiểm tra client certificate.

Mẫu:

~~~java
KeyStore keys = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("server.p12"))) {
    keys.load(in, "changeit".toCharArray());
}

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
    KeyManagerFactory.getDefaultAlgorithm());
kmf.init(keys, "changeit".toCharArray());

SSLContext serverTls = SSLContext.getInstance("TLS");
serverTls.init(kmf.getKeyManagers(), null, null);
~~~

Đây là **snippet** cần imports `java.security.KeyStore`, `java.io.InputStream`, `java.nio.file.*` và `javax.net.ssl.*`; không phải chương trình độc lập.

### 6.2. Client SSLContext

Ở client:
- `TrustManagerFactory` được khởi tạo từ `client-trust.p12`.
- `SSLContext.init(null, tmf.getTrustManagers(), null)` không đưa client private key, vì **không yêu cầu mTLS** trong bài.
- TrustManagers kiểm tra server certificate; HTTPS endpoint identification/hostname verification tiếp tục được Java `HttpClient` áp dụng theo chính sách HTTPS.

~~~java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(
        Path.of("client-trust.p12"))) {
    trust.load(in, "changeit".toCharArray());
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
    TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext clientTls = SSLContext.getInstance("TLS");
clientTls.init(null, tmf.getTrustManagers(), null);
~~~

Cũng là **snippet**, sử dụng `java.security`, `java.nio.file`, `java.io`, `javax.net.ssl`. Với production, truststore nên chứa CA/trust anchors đúng policy của tổ chức, không một certificate tự ký vừa sinh tùy tiện.

**Cảnh báo:** gọi `SSLContext.setDefault(...)` có thể ảnh hưởng toàn JVM và các thư viện khác. Khi chỉ muốn tin certificate thử nghiệm cho **một HttpClient**, hãy gắn `sslContext(clientTls)` trên **client builder cụ thể**, không thay đổi default global.

## 7. `HttpsServer`, `HttpsConfigurator` và `HttpsParameters`

### 7.1. Tạo HTTPS server

Cách tạo:

~~~java
HttpsServer server = HttpsServer.create(
    new InetSocketAddress(
        InetAddress.getByName("127.0.0.1"), 0),
    0);
~~~

Lệnh ở trên tạo server bind **loopback IPv4** và yêu cầu OS chọn cổng còn trống bằng `0`. Tham số `backlog=0` để implementation chọn giá trị mặc định phù hợp. Đây là **snippet** cần import `com.sun.net.httpserver.HttpsServer` và `java.net.*`.

**Bind loopback không giống bind công khai:** `127.0.0.1` chỉ nhận từ máy cục bộ. Production có thể bind địa chỉ cụ thể và phải kèm firewall/network policy, TLS identity hợp lệ và authorization. Không dùng `0.0.0.0` theo thói quen trong bài thực hành có private key giả.

### 7.2. Gắn HttpsConfigurator

~~~java
server.setHttpsConfigurator(new HttpsConfigurator(serverTls) {
    @Override
    public void configure(HttpsParameters params) {
        SSLParameters settings =
            getSSLContext().getDefaultSSLParameters();
        params.setSSLParameters(settings);
    }
});
~~~

**Điều này là bắt buộc về vai trò:** `HttpsServer` cần một `HttpsConfigurator` liên kết với `SSLContext` đã khởi tạo. Javadoc Java 17 nói `HttpsConfigurator.configure(HttpsParameters)` được gọi khi HTTPS connection mới đang được thiết lập; callback cung cấp TLS settings cho connection. Nếu override, cần gọi `params.setSSLParameters(settings)` để truyền toàn bộ SSL parameters.

**Không đặt cấu hình TLS bên trong `HttpHandler`** sau khi đã nhận request, vì lúc đó TLS handshake đã thành công hoặc connection đã được cấp. Certificate selection/protocol/ciphers là trách nhiệm handshake, không phải response header.

### 7.3. SSLParameters từ SSLContext

`getSSLContext().getDefaultSSLParameters()` trả **bản sao** cấu hình mặc định của context, gồm các protocols/cipher suites hiện đang được enable theo provider/security policy.

Ví dụ chỉ có giá trị khi **đã biết** tính tương thích của clients:

~~~java
SSLParameters tls = getSSLContext().getDefaultSSLParameters();
// Chỉ ví dụ ràng buộc protocol khi đã kiểm tra hỗ trợ:
tls.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
params.setSSLParameters(tls);
~~~

Đây là snippet **nằm trong configure(...)**, không phải code độc lập. `TLSv1.3` hỗ trợ trong nhiều JDK hiện đại, nhưng phải kiểm tra provider/policy; TLS 1.2 là một protocol bắt buộc hỗ trợ theo Java 17 SSLContext contract. Không tự bật TLS 1.0/1.1 hoặc yếu tố cryptography cũ chỉ để test qua.

**Khi có yêu cầu mTLS**, có thể cấu hình `SSLParameters.setNeedClientAuth(true)`, nhưng server `SSLContext` phải có **TrustManagers để tin client certificates**. Nếu thiếu trust anchors/KeyManager của client, handshake thất bại. Mục 11 giải thích cách thêm mTLS đúng ranh giới mà không biến bài server-auth thành một bài client-certificate khác.

### 7.4. Địa chỉ/ports và TLS sessions

- `HttpsParameters.getClientAddress()` cho biết địa chỉ mạng của peer đang kết nối theo API; **không phải identity đã được certificate chứng minh**.
- `HttpsExchange.getSSLSession()` cho phép quan sát TLS session của một exchange (ví dụ `getProtocol()`). Đừng log raw session IDs/peer certificates tùy tiện trong production.
- `server.getAddress().getPort()` trả cổng OS đã chọn sau bind; phù hợp viết test portable.
- `server.setExecutor(executor)` có thể cấp executor xử lý các HTTP requests; `server.stop(delay)` dừng HTTP listener/đóng các exchanges theo policy, **không tự shutdown executor do ứng dụng sở hữu**.

## 8. Ví dụ hoàn chỉnh: HTTPS loopback với client tin cậy và client không tin cậy

Đây là chương trình **Java 17+ đã biên dịch và chạy thật**. Nó:
1. Đọc `server.p12` để tạo **server SSLContext** (có private key).
2. Đọc `client-trust.p12` để tạo **client SSLContext** (chỉ tin self-signed certificate của bài).
3. Tạo `HttpsServer` trên `127.0.0.1`, gắn `HttpsConfigurator` và xử lý `GET /hello`.
4. Client tạo request `https://127.0.0.1:<port>/hello` bằng `HttpClient.newBuilder().sslContext(clientTls)`; certificate có IP SAN khớp.
5. In response status, body, HTTP version và chứng cứ handler quan sát được TLS session.
6. Thử `HttpClient.newHttpClient()` **không** có truststore custom: trong môi trường thử nghiệm certificate chưa được tin, handshake bị từ chối.
7. Dừng server trong `finally`, không để test process mở listener.

**Các file keystore phải được tạo từ mục 5 trước**. Program không tải certificate từ mạng và không tắt TLS validation.

### 8.1. Source độc lập: `LocalHttpsDemo.java`

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsExchange;
import com.sun.net.httpserver.HttpsParameters;
import com.sun.net.httpserver.HttpsServer;
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
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.TrustManagerFactory;

public class LocalHttpsDemo {
    private static final char[] PASSWORD = "changeit".toCharArray();

    static KeyStore loadStore(Path path) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            store.load(in, PASSWORD);
        }
        return store;
    }

    static SSLContext serverContext(Path serverKeys) throws Exception {
        KeyStore keys = loadStore(serverKeys);
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, PASSWORD);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), null, null);
        return context;
    }

    static SSLContext clientContext(Path serverTrust) throws Exception {
        KeyStore trust = loadStore(serverTrust);
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), null);
        return context;
    }

    static void handle(HttpExchange exchange,
            AtomicReference<String> negotiatedProtocol)
            throws java.io.IOException {
        try {
            if (!(exchange instanceof HttpsExchange)) {
                throw new java.io.IOException("Expected HTTPS");
            }
            negotiatedProtocol.set(
                ((HttpsExchange) exchange).getSSLSession().getProtocol());

            if (!"GET".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "GET");
                exchange.sendResponseHeaders(405, -1);
                return;
            }
            byte[] body =
                "Hello over HTTPS".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.out.println(
                "Usage: java LocalHttpsDemo server.p12 client-trust.p12");
            return;
        }

        SSLContext serverTls = serverContext(Path.of(args[0]));
        SSLContext clientTls = clientContext(Path.of(args[1]));
        AtomicReference<String> negotiatedProtocol =
            new AtomicReference<>();

        HttpsServer server = HttpsServer.create(new InetSocketAddress(
            InetAddress.getByName("127.0.0.1"), 0), 0);
        server.setHttpsConfigurator(new HttpsConfigurator(serverTls) {
            @Override
            public void configure(HttpsParameters params) {
                SSLParameters tls =
                    getSSLContext().getDefaultSSLParameters();
                params.setSSLParameters(tls);
            }
        });
        server.createContext("/hello",
            exchange -> handle(exchange, negotiatedProtocol));
        server.start();
        try {
            URI endpoint = URI.create(
                "https://127.0.0.1:" + server.getAddress().getPort()
                + "/hello");
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(5))
                .GET().build();
            HttpClient client = HttpClient.newBuilder()
                .sslContext(clientTls)
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
            HttpResponse<String> response = client.send(request,
                HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));
            System.out.println("HTTPS status: " + response.statusCode());
            System.out.println("HTTPS body: " + response.body());
            System.out.println("HTTP version: " + response.version());
            System.out.println("TLS active: "
                + negotiatedProtocol.get().startsWith("TLSv1."));

            boolean rejected = false;
            try {
                HttpClient.newHttpClient().send(request,
                    HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
            } catch (SSLHandshakeException expected) {
                rejected = true;
            }
            System.out.println(
                "Untrusted certificate rejected: " + rejected);
        } finally {
            server.stop(0);
        }
    }
}
~~~

### 8.2. Biên dịch, chạy

Đảm bảo đã có ba file `server.p12`, `server.crt`, `client-trust.p12` từ lệnh `keytool` ở mục 5. Lưu source ở cùng thư mục.

~~~bash
javac --release 17 -encoding UTF-8 LocalHttpsDemo.java
java LocalHttpsDemo server.p12 client-trust.p12
~~~

Compiler mới hơn dùng `--release 17` để xác minh code chỉ gọi **API có trong Java 17**. Nếu đang dùng JDK 17 thật, có thể dùng `javac -encoding UTF-8 LocalHttpsDemo.java`.

**Stdout đã kiểm thử thực tế** với keytool-generated self-signed certificate và HTTP client/server trên TCP loopback:

~~~text
HTTPS status: 200
HTTPS body: Hello over HTTPS
HTTP version: HTTP_1_1
TLS active: true
Untrusted certificate rejected: true
~~~

Trong lần kiểm tra, các file test được tạo trong một thư mục tạm và xóa sau khi chạy. Các dòng trên không chứa cổng ngẫu nhiên hoặc protocol version chi tiết để giữ output ổn định; chương trình kiểm tra `SSLSession.getProtocol().startsWith("TLSv1.")`, **không** assert TLS 1.3 cụ thể. Nếu JDK policy của bạn hỗ trợ TLS 1.2 nhưng không TLS 1.3, vẫn có thể là HTTPS hợp lệ với TLS 1.2.

**Điều kiện cho dòng cuối:** trong môi trường máy thử nghiệm, certificate mới sinh **chưa có trong default JVM truststore**. Nếu người chạy đã import certificate vào default truststore, thay đổi `javax.net.ssl.trustStore` của toàn JVM hoặc cài đặt một TLS policy khác, dòng `Untrusted certificate rejected` có thể là `false`; không kết luận mã sai chỉ vì máy đã có trust anchor. Ví dụ intentionally không thay thế toàn cục truststore.

### 8.3. Diễn giải từng bước

1. **LoadStore:** đọc PKCS12 trong `try-with-resources` để đóng `InputStream`; password `changeit` chỉ dành cho demo.
2. **serverContext:** `KeyManagerFactory` lấy private key/certificate từ `server.p12`; `context.init(kmf.getKeyManagers(), null, null)` chuẩn bị server TLS identity.
3. **clientContext:** `TrustManagerFactory` lấy trusted certificate từ `client-trust.p12`; `context.init(null, tmf.getTrustManagers(), null)` không cấp client certificate, đủ cho HTTPS xác thực server.
4. **HttpsServer.create:** bind `127.0.0.1:0`; OS cấp port. Server không có hostname `api.example.org` công khai.
5. **HttpsConfigurator:** lấy `getDefaultSSLParameters()` từ server TLS context và gọi `params.setSSLParameters(tls)` cho connection.
6. **handle:** chỉ nhận GET; nếu method khác thì `405` và `Allow: GET`. Với GET, trả body byte UTF-8 đúng số byte ở `sendResponseHeaders(200, body.length)`.
7. **HttpsExchange:** đọc `getSSLSession().getProtocol()`; server handler chỉ có TLS session sau khi HTTPS handshake thành công.
8. **HttpClient SSLContext:** client tin **đúng certificate thử nghiệm**, không dùng trust-all; Java client vẫn kiểm tra IP SAN `127.0.0.1` theo HTTPS identity policy.
9. **HTTP version:** `HTTP_1_1` là version được yêu cầu và thực tế server nhỏ của JDK trả về; nó **khác với TLS version**. `HTTP_1_1` không có nghĩa TLS 1.1.
10. **Thử client mặc định:** vì certificate tự ký chưa được default truststore chấp nhận, `send` ném `SSLHandshakeException`; handler không được gọi thành công cho request ấy.
11. **Cleanup:** `server.stop(0)` dừng server dù test chính hay test âm tính có lỗi; ví dụ không tự tạo executor ngoài cần shutdown.

### 8.4. Vì sao dùng `HttpsExchange` thay vì `HttpExchange` thuần?

`HttpsExchange` là subclass của `HttpExchange` và cung cấp `getSSLSession()`. Handler signature chuẩn vẫn nhận `HttpExchange`, nên ta kiểm tra `instanceof HttpsExchange` rồi cast khi thực sự cần quan sát TLS properties.

Không dùng `getSSLSession()` làm bằng chứng đã kiểm tra **quyền ứng dụng**. TLS session cho biết transport/peer cryptographic context; muốn xác thực access token hoặc cookie, phải triển khai HTTP authentication và authorization riêng.

### 8.5. Vì sao không in raw certificate hay SSL session ID?

Bài chỉ cần quan sát protocol có dạng TLS và response thật. In toàn bộ SSLSession/certificate/handshake logs trong ứng dụng production có thể làm lộ metadata nhạy cảm, tăng log volume hoặc gây khó kiểm soát. Dùng thông tin rút gọn: negotiated TLS version, cipher family và HTTP status/latency theo policy; không lưu private keys, raw token hoặc password.

## 9. Phân biệt HTTP version, TLS version và certificate identity

Ba khái niệm này thường bị lẫn nhau:

| Thuộc tính | Ví dụ | Kiểm tra tại đâu? |
|---|---|---|
| HTTP protocol version | `HTTP_1_1`, `HTTP_2` | `HttpResponse.version()` |
| TLS negotiated protocol | `TLSv1.2`, `TLSv1.3` | `HttpsExchange.getSSLSession().getProtocol()` |
| TLS certificate identity | SAN `IP:127.0.0.1` / `DNS:localhost` | Certificate và HTTPS endpoint identification |
| Server TCP address | `127.0.0.1:port` | `HttpsServer.getAddress()` |
| HTTP resource | `/hello` | `HttpExchange.getRequestURI()` |
| HTTP status | `200`, `405`, `404` | `HttpResponse.statusCode()` hoặc `sendResponseHeaders` |

**HTTPS không có nghĩa HTTP/2.** Server `jdk.httpserver` đơn giản chủ yếu phục vụ HTTP/1.1; một kết nối HTTPS có thể thương lượng TLS 1.3 nhưng vẫn truyền HTTP/1.1. Khi thấy `HTTP_1_1`, đừng suy ra TLS đã bị hạ xuống 1.1.

**TLS handshake không phải HTTP response:** nếu certificate chưa được tin, client thường nhận `SSLHandshakeException` trước khi có `HttpResponse`. Không cố đọc `response.statusCode()==401` khi response chưa tồn tại.

## 10. HttpsConfigurator: cấu hình per-connection đúng thời điểm

### Tại sao `configure` nhận `HttpsParameters`?

`HttpsServer` phải quyết định TLS protocols, cipher suites và yêu cầu client-auth khi connection mới đang thiết lập, **trước** khi biết đầy đủ HTTP request content (vì HTTP chạy bên trong kênh đã giải mã). `HttpsConfigurator.configure(HttpsParameters)` được gọi trong quá trình thiết lập HTTPS connection.

Một `HttpsServer` có thể dùng:
- SSLContext đã được khởi tạo trước khi start.
- Default `SSLParameters` của context cho mỗi incoming connection.
- Điều chỉnh TLS protocol/cipher policy trên `SSLParameters` nếu có lý do tương thích và kiểm thử bảo mật.
- Cấu hình `needClientAuth/wantClientAuth` khi muốn mTLS, với server trust policy tương ứng.

### Không chọn TLS policy dựa trên HTTP header chưa nhận

Ví dụ **sai tư duy**: trong `HttpHandler.handle`, đọc `Authorization` rồi mới bật/tắt certificate validation cho connection đang phục vụ. Handshake đã xảy ra; HTTP header **không thể** quay ngược lại kiểm tra certificate TLS ban đầu.

Nếu muốn áp chính sách yêu cầu certificate tùy service, thường tách listeners/hosts/ports hoặc thiết kế TLS reverse proxy/gateway với policy được định nghĩa trước handshake. Không đặt các exception “bỏ TLS check nếu header X có giá trị Y” trong handler.

### Có thể dùng default HttpsConfigurator không override?

Có. `new HttpsConfigurator(serverTls)` đã sử dụng default SSLParameters theo Javadoc. Trong bài này **override** để minh họa rõ cách `getSSLContext().getDefaultSSLParameters()` và `params.setSSLParameters(...)` được gọi, vì đây là trọng tâm đề bài.

Khi override, **phải hoàn thành việc cấu hình parameters**; quên gọi `params.setSSLParameters(...)` có thể khiến TLS settings không được áp dụng như bạn nghĩ. Đừng trả về một `SSLParameters` rồi tưởng API nhận được — phương thức `configure` là `void`.

### Thận trọng với per-client policy

`HttpsParameters.getClientAddress()` có thể dùng xem remote socket address, nhưng nó **không phải danh tính đáng tin** để thay thế certificate/token authentication. Một client trong mạng có thể thay IP/NAT/proxy; trong nhiều kiến trúc địa chỉ peer chỉ là reverse proxy.

Nếu một hệ thống cần nhiều certificate theo SNI/virtual host, key manager phải có chiến lược chọn alias theo TLS handshake; không nên viết if-else trong HTTP handler để đổi certificate sau handshake.

## 11. Mở rộng mTLS: biết điểm khác, không tự bật trong demo

Ví dụ `LocalHttpsDemo` là **server-auth TLS**: server có private key/certificate, client tin server, server không yêu cầu certificate của client.

Với **mutual TLS**:
1. Client còn cần **keystore riêng** chứa client private key/certificate.
2. Server cần **truststore** tin issuer/CA của client certificate.
3. `SSLContext` của server phải được khởi tạo với **KeyManagers (server identity) và TrustManagers (client cert trust)**.
4. `SSLContext` của client phải có **KeyManagers (client identity) và TrustManagers (server cert trust)**.
5. Server `SSLParameters` đặt `setNeedClientAuth(true)` **trước** `params.setSSLParameters(...)`.
6. Khi handshake thành công, server có thể đọc peer principal/certificate qua TLS session và ánh xạ sang application identity/quyền.

Mẫu cấu hình server-side (snippet chỉ dùng khi serverTls đã chứa trust managers phù hợp):

~~~java
server.setHttpsConfigurator(new HttpsConfigurator(serverTls) {
    @Override
    public void configure(HttpsParameters params) {
        SSLParameters tls =
            getSSLContext().getDefaultSSLParameters();
        tls.setNeedClientAuth(true);
        params.setSSLParameters(tls);
    }
});
~~~

**Không sao chép snippet này vào demo mục 8 rồi mong test vẫn chạy**: client trong demo không cung cấp client certificate; mTLS bắt buộc sẽ khiến handshake thất bại. Và nếu server chỉ tạo `serverTls` với `init(kmf.getKeyManagers(), null, null)`, nó chưa có trust policy riêng cho chứng chỉ client của tổ chức.

### `needClientAuth` khác `wantClientAuth`

- `needClientAuth(true)`: bắt buộc có và xác minh certificate client; nếu thiếu/bị từ chối, TLS handshake thất bại.
- `wantClientAuth(true)`: hỏi/ưu tiên certificate client nhưng không bắt buộc trong mọi trường hợp.
- Cả hai là **TLS handshake policy**; thành công vẫn chưa tự động cấp quyền ứng dụng. Service phải map certificate identity sang principal/roles/scopes theo policy.

Không dùng certificate public của một client làm thay thế cho Authorization token nếu nghiệp vụ cần phân quyền người dùng. mTLS thường định danh **workload/service**, HTTP auth có thể định danh user/request.

## 12. Vòng đời HttpExchange và resource management

HTTPS chỉ thêm TLS; phần xử lý HTTP response vẫn theo hợp đồng `HttpExchange`.

### Đọc request và viết response

Một handler đúng thường:

1. Đọc method và URI/path.
2. Nếu có body, **đọc/giới hạn hoặc từ chối an toàn**. Không đưa body của client chưa biết kích thước vào bộ nhớ vô hạn.
3. Thiết lập response headers, chẳng hạn `Content-Type` và các security headers theo use case.
4. Gọi `sendResponseHeaders(status, length)`.
5. Ghi đúng bytes vào `getResponseBody()` rồi **đóng output stream/exchange**.

Trong demo, body đã có trước dưới dạng UTF-8 `byte[]` nên `body.length` là **số byte đúng**, không dùng `String.length()` để tính `Content-Length`. Nếu viết ít hơn số byte đã công bố, stream close có thể ném `IOException` và connection bị bỏ.

### `sendResponseHeaders(status, length)` có những bẫy nào?

| Độ dài truyền | Ý nghĩa cần hiểu theo JDK HttpExchange |
|---|---|
| `length > 0` | Response body có đúng số byte chỉ định; viết ít/hơn sẽ là lỗi |
| `length == 0` | Server dùng chunked transfer encoding cho HTTP/1.1, cho phép độ dài tùy ý |
| `length == -1` | Không gửi response body |
| `HEAD` hoặc status không có body | Phải tuân thủ HTTP semantics; không cố ghi body |

**Điểm gây nhầm:** `0` trong `sendResponseHeaders` **không đơn giản nghĩa là body rỗng**. Khi muốn không gửi body, `-1` thường là lựa chọn thích hợp theo API.

### Executor và việc dừng server

`HttpsServer` kế thừa cơ chế `HttpServer.setExecutor(...)` và `stop(int delay)`. Nếu ứng dụng cấp `ExecutorService` riêng để xử lý nhiều requests, nó phải quản lý việc đóng executor **tách biệt** với server. Trong chương trình nhỏ, ta không cấp executor riêng để giảm chi phí/độ phức tạp.

`server.stop(0)` dừng ngay listener của **test server** sau khi có response. Nó không xóa keystore, revoke certificate hay shutdown client pool. Trong service thật cần graceful shutdown có deadline, ngừng nhận requests mới, đợi in-flight handlers và dọn secrets/executor theo quy định.

**Không giữ private key password dưới dạng hard-coded `String` trong ứng dụng thật.** Demo dùng một `char[]` hằng chỉ để dễ tái lập. Với production nên dùng secret manager, giảm vòng đời của secrets trong memory và tuân thủ chính sách rotation.

## 13. Những lỗi phổ biến khi làm bài HTTPS cục bộ

| Triệu chứng | Khả năng nguyên nhân | Cách chẩn đoán/sửa |
|---|---|---|
| `FileNotFoundException` cho `server.p12` | Chạy Java khác working directory; file chưa tạo | Kiểm tra tên file, đường dẫn, quyền đọc |
| `IOException: keystore password was incorrect` | Mật khẩu store sai | Kiểm tra secret đúng, không tắt integrity |
| `UnrecoverableKeyException` | Password private key entry sai | Phân biệt `-storepass` và `-keypass` |
| Không có server private key phù hợp | Alias/certificate chain hoặc KeyManagers sai | `keytool -list -v` kiểm tra `PrivateKeyEntry` |
| `HttpsServer` thiếu configurator | Chưa gắn initialized SSLContext/TLS config | Gọi `setHttpsConfigurator(...)` trước `start()` |
| `SSLHandshakeException: PKIX path building failed` | Client chưa tin server certificate/CA | Import **public certificate** đúng vào truststore được client sử dụng |
| `SSLHandshakeException` với hostname mismatch | Certificate SAN không phù hợp host/IP URI | Regenerate cert với SAN đúng; không tắt hostname check |
| `CertificateExpiredException` | Certificate thử nghiệm hết hạn | Tạo lại cert và cập nhật client truststore |
| `No appropriate protocol` / handshake failure | TLS versions/ciphersuite policy không khớp | Kiểm tra enabled/supported TLS versions cả hai phía |
| `Connection refused` | Server chưa chạy, bind nhầm IP/port | Kiểm tra start, localhost port, firewall |
| `UnknownHostException` | URL hostname sai | Dùng `127.0.0.1` cho demo, hostname thật ở production |
| `404 Not Found` qua HTTPS | TLS thành công nhưng handler path không khớp | Kiểm tra `/hello` và context mappings |
| `405 Method Not Allowed` | Client dùng method khác GET | Thực hiện GET, xem `Allow: GET` |
| HTTP `200` nhưng body bị cắt | Length bytes sai/stream close sai | Ghi byte[] với `body.length` và đóng stream |
| HTTP version `HTTP_1_1` nhưng TLS 1.3 | **Không phải lỗi** | HTTP và TLS là giao thức khác tầng |
| Client không tin vì truststore mới nhưng `server.p12` vừa regenerate | Đã đổi certificate/key | Export lại `server.crt` và import cert mới đúng alias |
| HTTPS chạy nhưng `server.stop` treo/tràn threads | Handler/stream/executor quản lý kém | Giới hạn work, deadlines, đóng exchange, shutdown executor sở hữu |
| Client báo 401/403 | TLS thành công; application auth/authorization từ chối | Kiểm tra credential/token, không đổi TLS truststore vô cớ |

### Không dùng trust-all như “cách sửa nhanh”

Một ví dụ **nguy hiểm** thường thấy trên mạng là cài `X509TrustManager` mà `checkServerTrusted(...)` không làm gì, hoặc tắt endpoint identification. Điều này khiến **mọi certificate** có thể được chấp nhận và phá vỡ xác thực server. Với API tài chính, nội bộ hay thông tin nhạy cảm, đây là lỗ hổng nghiêm trọng.

Bài này dùng `TrustManagerFactory` từ **truststore riêng** nên vẫn thực hiện certificate validation. Dòng `Untrusted certificate rejected: true` chứng minh việc từ chối là hành vi **đúng**, không phải lỗi cần bỏ qua.

## 14. Quan sát TLS không tiết lộ secrets

Khi HTTPS handshake thất bại, hãy phân lớp:

~~~text
1) TCP connect thành công chưa?
       │
       ├── không: IP/port/firewall/route
       │
       ▼
2) TLS ClientHello / ServerHello có protocol chung?
       │
       ├── không: protocol/cipher policy mismatch
       │
       ▼
3) Server có certificate/private key phù hợp không?
       │
       ├── không: keystore/alias/keypass/cert policy
       │
       ▼
4) Client tin certificate và SAN có match hostname/IP?
       │
       ├── không: truststore/expiry/SAN/PKIX
       │
       ▼
5) HTTP handler có nhận request?
       │
       ├── không: routing/context/HTTP version/method
       │
       ▼
6) Application auth/business logic/status/body
~~~

Có thể bật JSSE debug **chỉ trong môi trường thử nghiệm**:

~~~bash
java -Djavax.net.debug=ssl:handshake LocalHttpsDemo server.p12 client-trust.p12
~~~

Output handshake có thể dài và chứa metadata certificate, peer, session/crypto information. **Không bật debug mức chi tiết trên production rồi lưu logs vô hạn**. Không dùng `javax.net.debug` như một cách sửa handshake: đây là diagnostic, không thay trust policy.

Để xem cụ thể protocol/cipher suite trong code, có thể đọc `HttpsExchange.getSSLSession().getProtocol()` và `getCipherSuite()` trong handler. Đừng hiểu cipher suite mạnh tự động chứng minh request đã được phép thực hiện.

## 15. Tình huống: vì sao server có cert đúng nhưng client vẫn thất bại?

### A. Tin certificate nhưng hostname sai

Giả sử client truststore đã import certificate cho `localhost`, nhưng URL gọi là `https://service.internal.invalid` hoặc IP không có trong SAN. **Truststore và endpoint identity là hai phép kiểm tra khác nhau**. Kết nối phải bị từ chối nếu identity không khớp, dù certificate chain hợp lệ.

**Cách sửa:** dùng URI đúng SAN hoặc cấp lại certificate có SAN hợp lệ cho endpoint; không chỉ thêm chứng chỉ vào truststore rồi bỏ qua hostname verification.

### B. URL là HTTP, server là HTTPS

Nếu gọi `http://127.0.0.1:port/hello` tới cổng chỉ chấp nhận TLS, client gửi **HTTP plaintext** nơi server đang mong TLS ClientHello. Bạn sẽ thấy connection reset/parse error, **không** có kết quả HTTP 200 như mong muốn.

**Cách sửa:** dùng scheme `https://`. Còn nếu server là `HttpServer` không TLS mà client gọi HTTPS thì cũng sai tầng protocol.

### C. Certificate server hợp lệ nhưng client default trust chưa có nó

Đây là tình huống bài thử: self-signed certificate **chưa nằm trong default trust anchors** của JVM. Client default phải từ chối TLS. Chỉ client được cấu hình custom truststore mới có thể tin chính xác cert của server thử nghiệm. Không thay default truststore toàn hệ thống chỉ để một bài học chạy.

### D. Server đã có PKCS12 nhưng TLS vẫn không hoạt động

Một `KeyStore` có certificate công khai nhưng **không có PrivateKeyEntry** không thể đóng vai trò danh tính server-auth. `SSLContext` server cần KeyManager có private key để chứng minh identity handshake. Dùng `keytool -list -v` để phân biệt `trustedCertEntry` và `PrivateKeyEntry`.

### E. mTLS bật nhầm

Nếu dùng `setNeedClientAuth(true)` trong configurator nhưng client không có client certificate, handshake fail trước HTTP. Đây **không** phải HTTP `401 Unauthorized`; cần cấp và tin client certificate hoặc tắt client-auth nếu yêu cầu chỉ là server-auth HTTPS.

## 16. Vận hành HTTPS server của JDK: phạm vi và giới hạn

`com.sun.net.httpserver` thích hợp cho **bài học, test harness, công cụ nội bộ gọn nhẹ**, demo embedded HTTP/HTTPS hoặc những use cases đơn giản có threat model rõ. Nó không thay thế tất cả tính năng production web servers như:
- TLS termination/gateway management với certificate rotation tự động.
- Authentication/OAuth/OIDC/mTLS policy ở quy mô lớn.
- HTTP/2/HTTP/3 features, multiplexing, advanced routing/proxy.
- Request limits, rate limiting, WAF/DoS protection và observability đầy đủ.
- Graceful rollout, health checks, load balancing, distributed tracing.
- Quản lý certificate issuance/revocation/OCSP/PKI và secure secrets.

Không hiểu sự tồn tại của `HttpsServer` là bảo đảm đáp ứng mọi yêu cầu bảo mật/khả năng mở rộng. Với production nên chọn kiến trúc đã review threat model: có thể dùng web server/framework được bảo trì hoặc reverse proxy TLS đáng tin trước backend, và vẫn kiểm tra authentication/authorization trong ứng dụng.

### Nếu HTTPS kết thúc tại reverse proxy?

Khi một reverse proxy terminate TLS:
- Client kiểm tra certificate của **proxy/gateway** cho hostname công khai.
- Backend có thể nói chuyện HTTP hoặc mTLS **riêng** với proxy.
- `HttpsServer` trong backend không tự thấy TLS session của client Internet nếu TLS đã kết thúc ở gateway.
- Forwarded identity headers (như `X-Client-Cert`) chỉ tin khi do proxy đã xác thực sinh ra, được strip/overwrite từ external requests và chặng proxy→backend được bảo vệ.

Trong bài này **không có proxy**: một JVM chạy cả HTTPS server và HTTP client, TLS là end-to-end qua loopback giữa hai thành phần demo.

## 17. Checklist triển khai và kiểm thử

1. Dùng JDK 17+ có module `jdk.httpserver` và `java.net.http`.
2. Tạo `server.p12` với private key/certificate, SAN đúng hostname/IP URI và EKU phù hợp.
3. Export `server.crt`, import vào **client-trust.p12**, giữ private key server bí mật.
4. Khởi tạo server `SSLContext` bằng `KeyManagerFactory` đúng keystore.
5. Tạo `HttpsServer` trên địa chỉ/cổng được phép; dùng loopback trong lab.
6. Gắn `HttpsConfigurator` chứa initialized server context **trước khi start**.
7. Nếu override `configure`, gọi `params.setSSLParameters(...)` và chỉ bật protocol/ciphers được policy cho phép.
8. Đăng ký `HttpHandler`, đọc method/path, ghi status/body length đúng byte và đóng exchange.
9. Khởi tạo client `SSLContext` bằng `TrustManagerFactory`; không dùng trust-all hoặc bỏ SAN validation.
10. Tạo `HttpClient` chỉ tin truststore lab, đặt connect/request timeouts.
11. Thực hiện `GET https://127.0.0.1:<port>/hello`; xác minh status=200, body và TLS session.
12. Chạy thử client mặc định không có trust anchor: trong môi trường cô lập phải từ chối self-signed certificate.
13. Kiểm tra âm tính SAN mismatch/expiry/truststore sai, nhưng không phát tán private key.
14. Dừng server, đóng request/response streams và executor do ứng dụng sở hữu.
15. Không đưa password test vào source production, không commit `.p12` chứa private key và không log secrets.
16. Khi deploy thật, thay self-signed ngắn hạn bằng certificate/PKI và quy trình rotation/phân quyền đã được phê duyệt.

## 18. Bài tập tự kiểm tra

1. Vì sao đổi `http://` thành `https://` nhưng vẫn dùng `HttpServer` không đủ để có HTTPS?
2. `HttpsServer` thuộc module JDK nào? `HttpClient` thuộc module nào?
3. Vai trò khác nhau của `HttpsConfigurator`, `SSLContext` và `HttpsParameters` là gì?
4. `HttpsConfigurator.configure(...)` chạy trước hay sau khi handler đã đọc HTTP header? Vì sao?
5. Server keystore phải chứa entry nào để làm server TLS identity: `PrivateKeyEntry` hay `trustedCertEntry`?
6. Vì sao **không** đưa `server.p12` cho client dù trong đó có public certificate?
7. `server.crt` và `client-trust.p12` khác nhau ở đâu?
8. Vì sao certificate `CN=localhost` không đủ để đảm bảo `https://127.0.0.1` hợp lệ trên HTTPS client hiện đại?
9. Khác biệt giữa `SAN=DNS:localhost` và `SAN=IP:127.0.0.1` là gì?
10. `SSLContext.getInstance("TLS")` có buộc negotiated version là TLS 1.3 không?
11. Nếu client tin self-signed certificate trong custom truststore nhưng default JVM không tin, hai client có thể có kết quả khác nhau không?
12. Dòng `Untrusted certificate rejected: true` trong demo có chứng minh code HTTPS an toàn cho production không? Vì sao?
13. `HttpsExchange.getSSLSession().getProtocol()` cho biết loại version nào? Nó có giống `HttpResponse.version()` không?
14. Trong `sendResponseHeaders(200, body.length)`, tại sao phải dùng `body.length` chứ không phải độ dài Java String?
15. `sendResponseHeaders(status, 0)` trong JDK HTTP server có chắc chỉ gửi body rỗng không?
16. Nếu bạn bật `SSLParameters.setNeedClientAuth(true)` nhưng client không có private key/certificate, chuyện gì thường xảy ra?
17. Server bật mTLS rồi mà chỉ có `KeyManagerFactory`, chưa có TrustManagers tin client cert. Cần thay đổi điều gì?
18. Gọi HTTPS URL mà bị `SSLHandshakeException` trước khi nhận response thì có HTTP status code để đọc không?
19. Khi test thấy `HTTP version: HTTP_1_1`, có phải TLS version là 1.1 không?
20. Vì sao `SSLContext.setDefault` không nên dùng tùy tiện trong bài thử khi chỉ một client cần custom truststore?
21. `HttpsServer.stop(0)` có shutdown mọi executor/connection pools của ứng dụng không?
22. Khi dùng reverse proxy chấm dứt TLS, backend `HttpsExchange` có tự nhìn thấy client certificate từ đường Internet không?
23. Khi xử lý `SSLHandshakeException` do hostname mismatch, có nên tắt hostname validation không?
24. Nếu muốn test một request `POST` có body lớn, ngoài TLS cần thêm các giới hạn/resource checks gì?
25. Vì sao chứng chỉ tự ký `-validity 2` thường chỉ hợp lý cho lab mà không phải production?

**Đáp án gợi ý:**
(1) cần TLS server identity/handshake, dùng `HttpsServer`; (2) `jdk.httpserver` và `java.net.http`; (3) cấu hình connection / TLS engines & managers / per-connection settings; (4) trước HTTP handler vì HTTP nằm trong TLS; (5) `PrivateKeyEntry`; (6) file chứa private key server; (7) public certificate vs truststore chứa trusted entry; (8) URI dùng IP cần IP SAN; (9) DNS name vs IP identity; (10) không, negotiated theo provider/policy; (11) có; (12) không, chỉ chứng minh trust validation hoạt động trong lab; (13) TLS protocol khác HTTP version; (14) UTF-8 có thể dùng nhiều byte/ký tự; (15) không, 0 có ý nghĩa chunked trong API; (16) TLS handshake thường fail; (17) cấp TrustManagers/CA tin client; (18) chưa có; (19) không; (20) ảnh hưởng toàn JVM; (21) không, owner của resources phải dọn riêng; (22) không nếu TLS đã terminate ở gateway, cần trust boundary rõ; (23) không, sửa SAN/endpoint/cert; (24) limit bytes, timeout, streaming, reject, cleanup; (25) expiry/rotation/PKI và secret management production cần quy trình đầy đủ.

## 19. Tổng kết

- `HttpsServer` là HTTP server có TLS của module `jdk.httpserver`, cần **`HttpsConfigurator`** với **`SSLContext`** đã được khởi tạo.
- **Server TLS identity** dùng `KeyManagerFactory` và **private key + cert trong `server.p12`**. **Client trust** dùng `TrustManagerFactory` từ **`client-trust.p12`**. Tuy cùng dạng PKCS12, chúng có nhiệm vụ và mức bảo mật khác nhau.
- `HttpsConfigurator.configure(HttpsParameters)` đưa **SSLParameters** tới incoming TLS connection; handler chỉ xử lý HTTP request **sau** handshake.
- Chứng chỉ self-signed trong lab có **SAN=IP:127.0.0.1**, tránh sai hostname. **Không tắt** certificate/hostname verification.
- HTTPS status 200/body, HTTP/1.1 và TLS protocol là **ba loại thông tin khác nhau**; lỗi TLS trust không phải HTTP response status 401.
- Server-auth TLS đủ cho bài thử; muốn **mTLS** phải cấu hình thêm client key và server trust policy, không chỉ bật `needClientAuth`.
- Thử nghiệm Java 17 đã xác nhận một client truststore riêng kết nối thành công, còn client mặc định từ chối certificate tự ký chưa được tin.
- Sử dụng server nhỏ của JDK đúng phạm vi; production phải có trust/PKI/certificate rotation, authorization, resource limits và vận hành an toàn.

### Tài liệu tham khảo

- [Oracle Java SE 17 — com.sun.net.httpserver package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html)
- [Oracle Java SE 17 — HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html)
- [Oracle Java SE 17 — HttpsConfigurator và configure(HttpsParameters)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html)
- [Oracle Java SE 17 — HttpsParameters](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsParameters.html)
- [Oracle Java SE 17 — HttpsExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsExchange.html)
- [Oracle Java SE 17 — HttpExchange.sendResponseHeaders và body lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
- [Oracle Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [Oracle Java SE 17 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html)
- [Oracle Java SE 17 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html)
- [Oracle Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [Oracle Java SE 17 — HttpClient.Builder.sslContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
