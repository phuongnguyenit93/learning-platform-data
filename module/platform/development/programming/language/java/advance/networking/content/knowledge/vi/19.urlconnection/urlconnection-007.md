# HttpsURLConnection với SSLSocketFactory và xác minh tên máy — Java 17

## 1. Bài toán: TLS mã hóa được nhưng bạn đã kết nối đúng máy chủ chưa?

Một Java client cần gọi dịch vụ nội bộ qua HTTPS. Máy chủ dùng chứng chỉ X.509 do CA riêng cấp hoặc một chứng chỉ thử nghiệm chưa có trong truststore mặc định. Ứng dụng có thể cấu hình `SSLSocketFactory` riêng cho `HttpsURLConnection` để tin cậy đúng CA/chứng chỉ đó. Nhưng ngay cả khi **chuỗi chứng chỉ đáng tin**, ứng dụng vẫn cần xác minh chứng chỉ ấy **được phát hành cho đúng hostname trong URL**.

Ví dụ một máy chủ trình bày chứng chỉ với `subjectAltName: DNS:localhost`:

```text
https://localhost:8443/hello     -> tên máy khớp DNS SAN
https://127.0.0.1:8443/hello     -> KHÔNG khớp: IP cần iPAddress SAN
```

Cả hai URL có thể trỏ đến cùng một loopback server. Nhưng từ góc nhìn xác thực HTTPS, **tên máy mà client yêu cầu là một phần danh tính dịch vụ**, không phải chi tiết trang trí. Nếu chỉ kiểm tra “chứng chỉ này có được tin cậy không?” mà bỏ qua tên máy, một server có chứng chỉ hợp lệ cho host khác có thể bị chấp nhận sai.

Bài này giúp bạn:

1. Hiểu `HttpsURLConnection`, `SSLContext`, `SSLSocketFactory`, `TrustManagerFactory`, truststore và `HostnameVerifier`.
2. Phân biệt **trust chain verification** với **hostname verification**.
3. Gắn `SSLSocketFactory` cho **một connection** mà không làm thay đổi cấu hình HTTPS của toàn JVM.
4. Hiểu `subjectAltName` (DNS/IP), SNI và những lỗi tên máy thường gặp.
5. Viết một ví dụ Java 17 chạy thật với **HTTPS server loopback**, tạo chứng chỉ qua `keytool` của JDK, cho kết nối hợp lệ thành công và kết nối sai tên bị từ chối.
6. Tránh các anti-pattern nguy hiểm như **trust-all certificate** hoặc `HostnameVerifier` luôn trả `true`.
7. Xử lý timeout, response streams, lỗi TLS, HTTP error, redirects và vòng đời kết nối.

**Phạm vi:** đây là API cổ điển `java.net.URLConnection / HttpURLConnection` mở rộng bằng `javax.net.ssl.HttpsURLConnection`, không phải `java.net.http.HttpClient` hiện đại. Hai API có cách cấu hình TLS khác nhau; không được dùng nhầm method giữa chúng.

## 2. Sơ đồ các lớp: ai quyết định điều gì?

```text
URL("https://api.example/...") 
        |
        v
HttpsURLConnection (extends HttpURLConnection)
  |  request method, headers, timeouts, input/error stream
  |
  +--- SSLSocketFactory ----> tạo TLS socket
  |         ^
  |         |
  |     SSLContext("TLS")
  |       |-- KeyManager(s): client certificate / mTLS nếu cần
  |       |-- TrustManager(s): kiểm tra chứng chỉ peer/trust chain
  |       +-- SecureRandom
  |
  +--- HTTPS hostname identification (mặc định BẬT)
  |       +-- HostnameVerifier nếu cần quyết định bổ sung
  |
  +--- TLS handshake -> HTTP request -> HTTP response
```

| Thành phần | API Java 17 | Trách nhiệm chính |
|---|---|---|
| `URL` | `java.net.URL` | Lưu địa chỉ tài nguyên, gồm scheme và hostname client muốn gọi |
| `URLConnection` | `java.net.URLConnection` | Cấu hình và mở kết nối tới resource |
| `HttpURLConnection` | `java.net.HttpURLConnection` | HTTP method, status, redirects, headers, response/error stream |
| `HttpsURLConnection` | `javax.net.ssl.HttpsURLConnection` | HTTPS + TLS-specific socket factory, hostname verifier, chứng chỉ/session |
| `SSLContext` | `javax.net.ssl.SSLContext` | Cấu hình provider/protocol, key/trust managers để tạo TLS sockets/engines |
| `SSLSocketFactory` | `javax.net.ssl.SSLSocketFactory` | Tạo `SSLSocket` có cấu hình TLS |
| `KeyManagerFactory` | `javax.net.ssl.KeyManagerFactory` | Tạo key managers từ key material, hữu ích cho server certificate hoặc client mTLS |
| `TrustManagerFactory` | `javax.net.ssl.TrustManagerFactory` | Tạo trust managers từ truststore, kiểm chứng certificate path theo policy |
| `KeyStore` | `java.security.KeyStore` | Kho chứng chỉ/public trust anchors hoặc private key entry tùy mục đích |
| `HostnameVerifier` | `javax.net.ssl.HostnameVerifier` | Giao diện quyết định hostname có phù hợp TLS peer session khi cơ chế hostname check cần gọi bổ sung |
| `SSLSession` | `javax.net.ssl.SSLSession` | Thông tin phiên TLS đã thiết lập (peer, cipher/protocol, session) |

**Hai câu hỏi bảo mật khác nhau:**

- **“Tôi có tin chứng chỉ/chuỗi này không?”** → TrustManager/PKIX trust path, CA/trust anchor, thời hạn, chữ ký, key usage, constraints…
- **“Chứng chỉ đáng tin ấy có thuộc đúng dịch vụ tôi muốn gọi không?”** → HTTPS hostname identity check đối chiếu URL host với danh tính trong chứng chỉ, ưu tiên SAN đúng loại.

Chỉ trả lời **câu thứ nhất** là chưa đủ. Ngược lại, một chứng chỉ có tên chính xác nhưng do CA không tin cậy phát hành cũng không đủ để kết nối bảo mật được chấp nhận.

## 3. `HttpsURLConnection` khác `HttpURLConnection` ở đâu?

Với một URL HTTPS chuẩn, Java trả về một `HttpsURLConnection` cụ thể từ `openConnection()`. Nó **kế thừa** các phương thức HTTP/URLConnection như `setRequestMethod`, `getResponseCode`, `getInputStream`, `getErrorStream`, `setConnectTimeout`, `setReadTimeout` và `disconnect`.

Bổ sung dành cho HTTPS bao gồm:

- `setSSLSocketFactory(SSLSocketFactory)` / `getSSLSocketFactory()`: factory riêng cho instance này.
- `setHostnameVerifier(HostnameVerifier)` / `getHostnameVerifier()`: verifier riêng cho instance, khi thực sự cần tùy biến có kiểm soát.
- `getCipherSuite()`: cipher suite đã dùng.
- `getServerCertificates()`, `getPeerPrincipal()`: danh tính/chứng chỉ peer của kết nối TLS.
- `getSSLSession()`: Optional của session (Java 17).
- `getDefaultSSLSocketFactory()` / `setDefaultSSLSocketFactory(...)` và các method default hostname verifier **static**: cấu hình mặc định cho instance mới; phạm vi toàn lớp/JVM, dễ gây ảnh hưởng ngoài dự kiến.

### Cấu hình trước khi mở kết nối

Mẫu tối thiểu:

```java
// Đoạn minh họa, 'factory' phải được tạo an toàn từ SSLContext.
HttpsURLConnection conn = (HttpsURLConnection)
        new URL("https://api.example.test/data").openConnection();
conn.setSSLSocketFactory(factory);
conn.setConnectTimeout(3000);
conn.setReadTimeout(3000);
conn.setRequestMethod("GET");

// getResponseCode() có thể kích hoạt kết nối TLS/HTTP thực tế.
int status = conn.getResponseCode();
```

Các lệnh `setSSLSocketFactory`, timeout, method, headers và redirect policy phải đặt **trước khi kết nối thực sự diễn ra**. `getResponseCode()` hoặc `getInputStream()` có thể kích hoạt implicit `connect()`. Đừng thiết lập hostname verifier/factory sau khi request đã được gửi và mong nó áp dụng hồi tố.

**Không cast bừa URL HTTP:** `new URL("http://...").openConnection()` không phải `HttpsURLConnection`; ép kiểu sẽ ném `ClassCastException`. Kiểm tra scheme là `https` khi yêu cầu transport bảo mật.

## 4. TLS handshake và xác minh server identity

Một HTTPS request có thể có tiến trình khái quát:

```mermaid
sequenceDiagram
  participant App as Java application
  participant Conn as HttpsURLConnection / JSSE
  participant TLS as HTTPS server
  App->>Conn: openConnection; setSSLSocketFactory
  App->>Conn: getResponseCode / getInputStream
  Conn->>TLS: TCP + TLS ClientHello (có thể có SNI)
  TLS-->>Conn: TLS handshake + chứng chỉ server
  Conn->>Conn: Verify trust chain / PKIX policy
  Conn->>Conn: Verify hostname từ URL vs certificate SAN
  alt Trust và hostname đều hợp lệ
    Conn->>TLS: Encrypted HTTP request
    TLS-->>Conn: Encrypted HTTP response
    Conn-->>App: status + headers + body
  else Trust hoặc identity thất bại
    Conn-->>App: SSLHandshakeException / SSLException
  end
```

Trên thực tế, một số bước có thể diễn ra trong quá trình TLS handshake, một số được HTTP/TLS adapter thực hiện tiếp. Thứ tự implementation chính xác tùy provider/JDK; điều **bất biến về security expectation** là ứng dụng không được xem HTTPS peer là đúng server cho tới khi **cả trust lẫn danh tính dịch vụ** được xác minh phù hợp.

**TLS khác HTTP status:** nếu TLS handshake thất bại, có thể chưa có HTTP request/response hợp lệ. Bạn không được mặc định lấy `getResponseCode()==401`, `403` hay `500` để biểu thị “certificate error”. Lỗi xác thực server thuộc tầng TLS/`IOException`.

### Không nhầm hostname, DNS/IP, SNI, certificate CN và SAN

- **Hostname trong URL**: tên mà ứng dụng mong giao tiếp, ví dụ `api.example.test`.
- **DNS resolution**: tìm một hoặc nhiều địa chỉ IP để kết nối; nhiều hostname có thể cùng trỏ tới một IP.
- **SNI (Server Name Indication)**: phần mở rộng TLS cho phép client truyền tên server mong muốn để server chọn certificate/config; **không tự thay thế xác minh identity**.
- **Certificate Subject CN**: trường tên chủ thể theo kiểu cũ; **không nên lấy CN làm nguồn duy nhất thay SAN**.
- **Subject Alternative Name (SAN)**: nơi khai báo nhiều danh tính DNS và IP của dịch vụ trong chứng chỉ hiện đại.

Một IP có thể phục vụ rất nhiều HTTPS sites. Việc đã kết nối tới đúng IP **không chứng minh** certificate đúng cho hostname bạn yêu cầu.

## 5. `SSLSocketFactory` có tác dụng gì?

`SSLSocketFactory` tạo ra các `SSLSocket` có những thiết lập TLS từ provider/`SSLContext`. Một factory có thể mang chính sách trust khác mặc định, key manager cho client certificate, cách tạo socket và những cấu hình TLS được hỗ trợ.

Mẫu xây dựng an toàn:

```text
Truststore có CA/certificate công khai đáng tin
   -> KeyStore.load(...)
   -> TrustManagerFactory.init(trustStore)
   -> SSLContext.getInstance("TLS")
   -> SSLContext.init(null, trustManagers, SecureRandom)
   -> SSLContext.getSocketFactory()
   -> HttpsURLConnection.setSSLSocketFactory(factory)
```

Chỉ định truststore riêng **không yêu cầu vô hiệu hóa hostname checking**. Bạn có thể tin một server certificate self-signed **cho môi trường test**, nhưng nếu URL host không khớp SAN vẫn phải bị từ chối.

### Sự khác nhau giữa “trust certificate” và “trust-all”

**Trust cụ thể:** truststore chứa public certificate hoặc CA nội bộ xác định. TrustManagerFactory dùng vật liệu tin cậy này để kiểm chứng certificate path. Với môi trường kiểm thử, việc tin cậy riêng certificate tự ký là hợp lý nếu kiểm soát đúng nguồn.

**Trust-all:** tạo một `X509TrustManager` có `checkServerTrusted(...)` rỗng, hoặc factory chấp nhận mọi certificate. Đây là **anti-pattern nghiêm trọng**: kết nối dễ bị man-in-the-middle, ngay cả nếu URL nhìn như HTTPS. Bài này **không** cung cấp trust-all code.

### Vì sao không sửa default global?

`HttpsURLConnection.setDefaultSSLSocketFactory(...)` là method static, tác động tới những **instance mới** dùng default của lớp, có thể ảnh hưởng thư viện khác cùng JVM. Thay global default hostname verifier còn nguy hiểm hơn. Khi chỉ cần gọi một API/truststore, dùng:

```java
conn.setSSLSocketFactory(context.getSocketFactory());
```

trên **connection cụ thể**, tránh phá vỡ chính sách trust của các kết nối HTTPS không liên quan. Các instance đã tạo trước thay đổi default không tự áp dụng cấu hình mới.

## 6. Truststore và keystore: cùng API nhưng khác mục đích

Trong Java, cả hai có thể dùng `KeyStore` nhưng nội dung và vai trò khác nhau:

| Vật liệu | Chứa gì? | Bên dùng | Dùng để làm gì? |
|---|---|---|---|
| **Server keystore** | Private key + certificate chain server | `KeyManagerFactory` của HTTPS server | Server chứng minh mình sở hữu private key cho certificate |
| **Client truststore** | Public CA certificate hoặc certificate được tin cậy | `TrustManagerFactory` của client | Client xác thực certificate chain phía server |
| **Client keystore** (khi mTLS) | Private key + certificate chain client | `KeyManagerFactory` của HTTPS client | Client trình bày danh tính của mình nếu server yêu cầu |
| **Server truststore** (khi mTLS) | CA/certificate client được chấp nhận | Trust manager phía server | Server xác thực client certificate |

**Không chuyển private key của server sang client** chỉ để client tin certificate. Trong demo, ta `keytool -exportcert` lấy **public certificate**, rồi `-importcert` vào **truststore riêng**. `server.p12` vẫn chỉ thuộc phía server và chứa private key.

### PKCS12 và JKS

`KeyStore.getInstance("PKCS12")` đọc định dạng PKCS #12 phổ biến, có thể chứa private key/certificate entries. JKS là định dạng Java truyền thống; không dựa vào default store type mà không kiểm tra, đặc biệt khi chạy trên các bản JDK khác nhau.

Ví dụ đọc truststore một cách có giới hạn:

```java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(trustPath)) {
    trust.load(input, passwordChars);
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, tmf.getTrustManagers(), new SecureRandom());
SSLSocketFactory factory = context.getSocketFactory();
```

Đoạn code minh họa có import `java.security.KeyStore`, `java.security.SecureRandom`, `java.nio.file.Files`, `java.nio.file.Path`, `java.io.InputStream` và `javax.net.ssl.*`. Đây là cấu hình **chỉ trust store mới** trong ví dụ; không tự động trộn với mọi trusted root của hệ thống. Nếu cần vừa giữ default CAs vừa tin CA riêng, hãy thiết kế trust material/chính sách rõ ràng thay vì làm mất hoặc bỏ qua trust checks.

## 7. Xác minh hostname: SAN DNS và SAN IP

Giả sử certificate chỉ có:

```text
Subject: CN=localhost
X509v3 Subject Alternative Name:
    DNS:localhost
```

Dự kiến:

| URL | Reference identity | Certificate SAN | Kết quả |
|---|---|---|---|
| `https://localhost:8443` | DNS name `localhost` | `DNS:localhost` | **Có thể khớp** nếu trust và TLS checks khác đều hợp lệ |
| `https://127.0.0.1:8443` | IP address `127.0.0.1` | Chỉ `DNS:localhost` | **Không khớp**, bị từ chối |
| `https://api.example.test` | DNS `api.example.test` | `DNS:localhost` | **Không khớp** |
| `https://foo.example.test` | DNS `foo.example.test` | `DNS:*.example.test` nếu có | Phụ thuộc quy tắc wildcard an toàn và policy |
| `https://[::1]:8443` | IPv6 literal `::1` | Không có `IP:::1` | **Không khớp** |

**Quy tắc vận hành:** nếu client thật sự truy cập bằng IP, certificate phải có **iPAddress SAN** tương ứng (ví dụ `IP:127.0.0.1`); `DNS:localhost` không là wildcard cho IP và ngược lại. Việc DNS phân giải `localhost` tới `127.0.0.1` không biến URL host IP thành DNS host.

Cách làm đúng khi certificate không khớp:

- Dùng **đúng hostname** đã được chứng chỉ cấp phép và DNS/route thích hợp.
- Hoặc **phát hành lại certificate** có SAN đúng cho hostname/IP chính thức.
- Kiểm tra load balancer/proxy đang đưa ra certificate tương ứng với SNI hay không.
- Không sửa `HostnameVerifier` thành luôn trả true để “chữa nhanh” lỗi.

RFC 9525 (Service Identity in TLS, 2023) mô tả các phương pháp hiện đại về xác minh danh tính dịch vụ, trong đó tên DNS và IP phải được kiểm tra theo loại identifier phù hợp. JDK 17 có implementation HTTPS hostname checking riêng theo API, vì vậy không mặc định rằng mọi chi tiết của RFC ban hành sau đều đã được áp dụng giống nhau trong JDK 17; ứng dụng nên giữ cấu hình bảo mật mặc định, kiểm thử chứng chỉ thật và chính sách provider.

### Tên máy không phải HTTP Host header

Một request có thể có `Host` hoặc `:authority` trong HTTP tùy version, nhưng đây **không phải nút tắt xác minh TLS**. Thay `Host` header mà vẫn kết nối URL khác có thể tạo tình huống routing khó đoán hoặc lỗi security. Reference identity nên gắn với URL/endpoint thực sự và policy của client, không được tùy tiện thay bằng tên không tin cậy trong response.

## 8. `HostnameVerifier`: khi nào cần, khi nào tuyệt đối tránh?

Interface `HostnameVerifier` có một method:

```java
boolean verify(String hostname, SSLSession session);
```

Java documentation mô tả verifier có thể được gọi khi các quy tắc hostname verification mặc định **không xác định được một match chấp nhận được**. `hostname` là tên muốn kiểm chứng; `session` là TLS session tương ứng. Verifier trả `true` nếu hostname được chấp nhận, `false` nếu không.

**Khuyến nghị:** trong hầu hết ứng dụng, **không override** verifier. `HttpsURLConnection` có logic mặc định để xác minh host trong URL với certificate. Khi cần đổi trust anchors, chỉ thay `SSLSocketFactory` (dùng TrustManagerFactory đúng), **giữ hostname checking mặc định**.

### Anti-pattern nguy hiểm

Một `HostnameVerifier` có logic “luôn trả true” khiến URL `https://bank.example` có thể được chấp nhận khi peer trình certificate cho host khác. Kết hợp với trust-all càng làm HTTPS mất phần lớn ý nghĩa bảo vệ chống MITM. **Không dùng kể cả trong code mẫu được copy sang production**.

Tương tự, không gọi `HttpsURLConnection.setDefaultHostnameVerifier(...)` với verifier nới lỏng: đây là thay đổi phạm vi rộng, có thể làm các HTTP clients khác trong JVM chấp nhận tên máy sai.

### Trường hợp cần verifier custom có kiểm soát

Một môi trường legacy đặc biệt có thể có cơ chế identity bổ sung được thiết kế/kiểm toán kỹ; khi đó một verifier custom phải xử lý tên máy, session, certificate chain và policy cụ thể. Nhưng việc thay đổi cơ chế mặc định đòi hỏi threat model, unit/integration tests, review bảo mật và kế hoạch loại bỏ ngoại lệ. **Đừng dùng custom verifier chỉ vì cert self-signed**: self-signed là vấn đề **truststore**, còn hostname mismatch là vấn đề **identity**.

### Gọi verifier default bằng tay có đủ không?

Không nên tự viết một check ad-hoc chỉ dựa trên `getPeerPrincipal().getName()` hay `CN`, rồi cho qua certificate. Chữ ký và trust chain, SAN, hostname, EKU và nhiều policy khác cần được JSSE/HTTPS verifier xử lý đúng. Sử dụng default HTTPS stack an toàn đáng tin cậy hơn việc lập trình regex match certificate subject.

## 9. Demo đầy đủ Java 17: HTTPS loopback, truststore riêng, mismatch bị từ chối

Ví dụ này **chạy trên JDK 17** và chỉ dùng module JDK tích hợp `java.base`, `jdk.httpserver`:

- `keytool` tạo một **demo RSA certificate** với `SAN=DNS:localhost`, server keystore `server.p12`.
- Export **public certificate** sang `server.crt`, import vào `trust.p12` làm truststore chỉ cho client demo.
- Dựng HTTPS server loopback dùng `com.sun.net.httpserver.HttpsServer`.
- Tạo client `SSLContext` với `TrustManagerFactory` đọc `trust.p12`.
- Mở hai `HttpsURLConnection` dùng **cùng SSLSocketFactory riêng**, không tắt default hostname verification.
- `https://localhost:port/hello` thành công với HTTP 200 và body `HTTPS OK`.
- `https://127.0.0.1:port/hello` bị từ chối vì certificate **chỉ có DNS SAN**, không có IP SAN.
- Chương trình tự kiểm tra kỳ vọng và sẽ báo lỗi nếu một response/hostname policy lệch.

Đây là **test/demo**, không phải public HTTPS service. Password `changeit` chỉ cho keystore được tạo tạm tại máy học và **không** phải lựa chọn bí mật sản xuất.

### 9.1. Tạo keystore và truststore bằng keytool

Chạy trong **một thư mục thử nghiệm riêng**. Các lệnh dưới đây viết trên một dòng để dễ dùng cả Bash lẫn PowerShell (nếu `keytool` từ JDK đã có trong `PATH`):

```bash
keytool -genkeypair -alias localhost-demo -keyalg RSA -keysize 2048 -validity 2 -storetype PKCS12 -keystore server.p12 -storepass changeit -keypass changeit -dname "CN=localhost, OU=Demo, O=Example, C=VN" -ext "SAN=DNS:localhost" -noprompt

keytool -exportcert -alias localhost-demo -keystore server.p12 -storetype PKCS12 -storepass changeit -file server.crt

keytool -importcert -alias localhost-demo -file server.crt -keystore trust.p12 -storetype PKCS12 -storepass changeit -noprompt
```

**Đọc ý nghĩa:**

1. `-genkeypair` sinh private key + certificate tự ký vào `server.p12` (mật khẩu demo).
2. `-ext SAN=DNS:localhost` ghi **DNS SAN** quan trọng vào certificate. `CN=localhost` trong Subject không thay thế SAN.
3. `-exportcert` xuất public certificate, **không xuất private key**.
4. `-importcert` đưa public certificate vào `trust.p12`; client có một trust anchor cụ thể.
5. Certificate hiệu lực chỉ 2 ngày vì phục vụ bài thử; chạy sau khi hết hạn cần **tạo lại keystore/truststore**. Với hệ thống thật, dùng CA/PKI và rotation phù hợp.
6. Đừng commit `server.p12` hay password vào Git; xóa artifacts demo sau khi chạy.

### 9.2. Mã hoàn chỉnh: HttpsHostnameDemo.java

```java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLException;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManagerFactory;

public class HttpsHostnameDemo {
    private static KeyStore loadStore(Path path, char[] password)
            throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            store.load(in, password);
        }
        return store;
    }

    private static SSLContext serverContext(
            Path keyStorePath, char[] password) throws Exception {
        KeyStore keys = loadStore(keyStorePath, password);
        KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keyManagers.init(keys, password);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keyManagers.getKeyManagers(), null,
                new SecureRandom());
        return context;
    }

    private static SSLSocketFactory clientFactory(
            Path trustStorePath, char[] password) throws Exception {
        KeyStore trust = loadStore(trustStorePath, password);
        TrustManagerFactory trustManagers =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm());
        trustManagers.init(trust);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, trustManagers.getTrustManagers(),
                new SecureRandom());
        return context.getSocketFactory();
    }

    private static HttpsURLConnection connection(
            String address, SSLSocketFactory factory)
            throws IOException {
        HttpsURLConnection conn = (HttpsURLConnection)
                new URL(address).openConnection(Proxy.NO_PROXY);
        conn.setSSLSocketFactory(factory);
        // Giữ HostnameVerifier mặc định của JDK.
        conn.setConnectTimeout(3000);
        conn.setReadTimeout(3000);
        conn.setInstanceFollowRedirects(false);
        return conn;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: HttpsHostnameDemo server.p12 trust.p12 password");
        }
        char[] password = args[2].toCharArray();
        SSLContext tlsServer = serverContext(
                Path.of(args[0]), password);
        SSLSocketFactory tlsClient = clientFactory(
                Path.of(args[1]), password);

        HttpsServer server = HttpsServer.create(
                new InetSocketAddress(
                        InetAddress.getByAddress(
                                new byte[] {127, 0, 0, 1}), 0), 0);
        server.setHttpsConfigurator(
                new HttpsConfigurator(tlsServer));
        server.createContext("/hello", exchange -> {
            byte[] body = "HTTPS OK".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
            exchange.close();
        });
        server.start();

        try {
            int port = server.getAddress().getPort();
            HttpsURLConnection good = connection(
                    "https://localhost:" + port + "/hello",
                    tlsClient);
            try {
                int status = good.getResponseCode();
                boolean peerSubjectHasLocalhost =
                        good.getPeerPrincipal().getName()
                                .contains("CN=localhost");
                String result;
                try (InputStream in = good.getInputStream()) {
                    result = new String(
                            in.readAllBytes(), StandardCharsets.UTF_8);
                }
                if (status != 200 || !"HTTPS OK".equals(result)) {
                    throw new IllegalStateException(
                            "Unexpected HTTPS response");
                }
                System.out.println("Trusted localhost: " + status);
                System.out.println("Response body: " + result);
                System.out.println("Peer subject contains localhost: "
                        + peerSubjectHasLocalhost);
            } finally {
                good.disconnect();
            }

            HttpsURLConnection wrongName = connection(
                    "https://127.0.0.1:" + port + "/hello",
                    tlsClient);
            boolean rejected = false;
            try {
                wrongName.getResponseCode();
            } catch (SSLException expected) {
                rejected = true;
            } finally {
                wrongName.disconnect();
            }
            if (!rejected) {
                throw new IllegalStateException(
                        "IP mismatch was not rejected");
            }
            System.out.println("IP hostname mismatch rejected: true");
        } finally {
            server.stop(0);
        }
    }
}
```

### 9.3. Biên dịch và chạy

Trong cùng thư mục chứa Java source và hai file `.p12` đã tạo:

```bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 HttpsHostnameDemo.java
java --add-modules jdk.httpserver HttpsHostnameDemo server.p12 trust.p12 changeit
```

Module `jdk.httpserver` cần được thêm để dùng HTTPS server tích hợp trong JDK; `HttpsURLConnection`, JSSE và các lớp certificate nằm trong `java.base`. Bản thân client `HttpsURLConnection` **không cần** `jdk.httpserver` nếu ứng dụng thực không tự dựng server.

**Stdout chính xác khi chạy thành công với JDK 17 và socket loopback được phép:**

```text
Trusted localhost: 200
Response body: HTTPS OK
Peer subject contains localhost: true
IP hostname mismatch rejected: true
```

`keytool` có thể in thông báo riêng khi tạo/chuyển certificate; bốn dòng trên là **stdout của Java program**, không bao gồm output của keytool.

### 9.4. Vì sao demo dùng các tệp riêng?

`server.p12`: chứa **private key và server certificate**. `KeyManagerFactory` dùng nó để HTTPS server trình bày danh tính.

`server.crt`: **public certificate**, không mang private key.

`trust.p12`: truststore chỉ cho demo client. `TrustManagerFactory` lấy certificate đã import để kiểm chứng peer server. Đó là trust theo một certificate cụ thể, **không phải bỏ qua PKIX checks**.

`SSLContext.getInstance("TLS")` dùng provider để chọn các phiên bản/protocol TLS được bật theo chính sách runtime; không hardcode SSLv3/TLSv1.0 cũ. Không suy ra tên `"TLS"` buộc dùng duy nhất TLS 1.3. Với vận hành thật, kiểm soát JDK security updates, protocols/cipher suites theo chính sách.

### 9.5. Vì sao chứng chỉ đáng tin mà URL IP vẫn bị từ chối?

Certificate được import vào truststore: trust path đáp ứng đối với cả hai kết nối. Nhưng kết nối thứ hai yêu cầu **reference identity = 127.0.0.1**, trong khi chứng chỉ chỉ khai báo **DNS SAN localhost**. Vì vậy default HTTPS hostname verification bác bỏ việc coi certificate ấy là định danh của URL IP.

Đây là điều bài học muốn chứng minh: **trust store đúng không có nghĩa tên máy nào cũng hợp lệ**.

### 9.6. `getPeerPrincipal()` ở ví dụ chỉ là quan sát

Dòng `Peer subject contains localhost: true` đọc `getPeerPrincipal().getName()` sau khi kết nối TLS thành công và trước khi đóng response stream. Nó giúp quan sát một phần subject nhưng **không phải phép xác minh hostname chính** và **không thay thế kiểm tra SAN**. Kiểm tra hostname an toàn do JDK HTTPS stack thực hiện.

Khi debug, gọi `getPeerPrincipal()`/`getCipherSuite()` **sau khi connection đã được thiết lập và còn hợp lệ**. Các method này có thể ném `IllegalStateException` nếu chưa connected, hoặc session/resource không còn có thể truy xuất trong trạng thái hiện tại. Không lấy string CN rồi tự quyết định cho phép kết nối.

### 9.7. Vì sao dùng `openConnection(Proxy.NO_PROXY)`?

Demo cố ý kết nối loopback **trực tiếp** để không lệ thuộc proxy môi trường; `Proxy.NO_PROXY` chỉ tuyến direct của kết nối thử nghiệm. Production có thể bắt buộc proxy egress: **không copy `Proxy.NO_PROXY` một cách mù quáng** để bỏ qua chính sách doanh nghiệp. Khi dùng proxy HTTPS, các bước CONNECT, TLS trust và hostname verification vẫn cần đúng.

### 9.8. Giới hạn trung thực

- Server chỉ tồn tại trong JVM, dùng certificate self-signed có thời hạn rất ngắn; không có public CA, mTLS, authentication application, rate limiting hoặc database.
- Không có HTTP load balancer, proxy, redirect hay hostname khác ngoài loopback; chỉ kiểm tra một truststore và một mismatch cụ thể.
- Bài test giả định `localhost` có thể truy cập loopback server IPv4 trên máy chạy. Môi trường không cho phép socket hoặc có thay đổi mapping `localhost`/firewall có thể gây lỗi mạng; đó **không** phải bằng chứng hostname verification bị tắt.
- Các lỗi TLS có thể có message cụ thể khác giữa provider/bản JDK; chương trình chỉ kiểm tra **loại `SSLException`** cho case sai tên, không cứng mã hóa exception message phụ thuộc implementation.
- Self-signed certificate chỉ nên dùng trong bài lab/kiểm thử có kiểm soát. Không gửi private key, truststore password thật hoặc certificate không tin cậy vào repository/public chat.

## 10. Kết nối HTTPS thực bằng URLConnection: mẫu sử dụng đúng lifecycle

Với một endpoint được quản trị, bước build client factory có thể được chia khỏi business code. Mẫu gọi sau minh họa cách dùng `HttpsURLConnection` **sau khi đã có** `SSLSocketFactory secureFactory` được tạo từ truststore chuẩn:

```java
// Minh họa trong phương thức có thể ném IOException; không độc lập.
URL url = new URL("https://api.example.test/data");
HttpsURLConnection conn =
        (HttpsURLConnection) url.openConnection();
conn.setSSLSocketFactory(secureFactory);
conn.setConnectTimeout(3000);
conn.setReadTimeout(5000);
conn.setInstanceFollowRedirects(false);
conn.setRequestMethod("GET");
conn.setRequestProperty("Accept", "application/json");

try {
    int status = conn.getResponseCode();
    InputStream stream = status >= 400
            ? conn.getErrorStream()
            : conn.getInputStream();

    if (stream != null) {
        try (InputStream in = stream) {
            // Đọc theo quota/charset/schema do ứng dụng định nghĩa.
        }
    }

    // Xử lý status, headers và kết quả nghiệp vụ riêng.
} finally {
    conn.disconnect();
}
```

**Những chi tiết cần hiểu:**

- `getResponseCode()` có thể tự kết nối/handshake; do đó cấu hình factory, timeouts, redirect và headers **trước** lời gọi này.
- `getInputStream()` có thể ném `IOException` cho HTTP error response; nếu server đã trả lỗi HTTP, có thể đọc `getErrorStream()` để lấy body lỗi (có thể `null`), trong khi lỗi TLS **không bắt buộc có HTTP error stream**.
- `getErrorStream()` không phải lựa chọn để “bắt lỗi certificate”; lỗi certificate xảy ra trước khi có response hợp lệ.
- `disconnect()` báo runtime không còn cần connection; nó không thay thế việc đóng input/output stream, và HTTP keep-alive/reuse tùy implementation.
- Với body lớn, cần size/time budget và streaming; `readAllBytes()` trong demo chỉ áp dụng cho body nhỏ cố định. Đừng gom response hàng gigabyte từ URL không tin cậy vào RAM.
- `setInstanceFollowRedirects(false)` ngăn client tự chuyển sang URL đích khác. Khi cho phép redirect, phải đánh giá hostname/trust cho **mỗi đích thực sự**, tránh token/credential bị chuyển nhầm host không đáng tin.

### Nên dùng cùng một SSLSocketFactory cho nhiều connections?

Có thể tái sử dụng một factory được tạo an toàn cho các kết nối phục vụ cùng trust/security policy; không cần nạp truststore và khởi tạo `SSLContext` mỗi request. Tuy nhiên, thay truststore động, chứng chỉ hết hạn hoặc CA rotation có thể đòi hỏi tạo lại context/factory theo policy và quan sát kết nối đang tồn tại. Không dựa vào việc sửa file `.p12` trên disk để mọi TLS connection đang mở tự đổi cấu hình.

## 11. Timeout, TLS errors và HTTP status là ba loại quan sát khác nhau

Một hệ thống HTTPS có nhiều điểm lỗi:

| Giai đoạn | Ví dụ lỗi | Kết quả Java có thể gặp | Hướng xử lý |
|---|---|---|---|
| URL validation | Scheme sai, URI malformed | `MalformedURLException`, `ClassCastException` nếu cast sai | Kiểm tra URL/host/scheme trước |
| DNS/route | Không resolve được hostname | `UnknownHostException` | Kiểm tra DNS/VPN/proxy |
| TCP connect | Không có service ở host:port | `ConnectException`, timeout | Kiểm tra endpoint/firewall/port |
| TLS trust | Certificate self-signed chưa tin, chain không đến root | `SSLHandshakeException` thường có `PKIX path building failed` trong cause | Cấu hình CA/truststore đúng, không trust-all |
| TLS identity | SAN không chứa URL hostname/IP | `SSLHandshakeException`/`SSLException` với message hostname mismatch | Dùng đúng tên hoặc phát hành lại cert SAN |
| TLS protocol | Version/cipher mismatch, handshake alert | `SSLHandshakeException` | Kiểm tra JDK/protocol/cipher policy |
| TLS certificate validity | Expired/not yet valid, CA constraints, EKU | `SSLHandshakeException` hoặc cause PKIX validation | Cấp lại chứng chỉ, đồng bộ thời gian, sửa chain |
| HTTP status | Server trả 401/403/404/500 | `getResponseCode()` trả status hoặc `getInputStream()` báo lỗi | Xử lý status và error stream theo API contract |
| App parsing | JSON sai schema, charset không khớp | Lỗi parser/application | Validate media type, schema, data |
| Timeout khi đã gửi | Mất response hoặc server xử lý chậm | `SocketTimeoutException`/`IOException` | Outcome có thể unknown; áp dụng retry/idempotency theo method |

**Quan trọng:** không xử lý mọi `SSLHandshakeException` như “hostname sai”. Có thể do trust chain, certificate date, TLS protocol/cipher, client authentication, hoặc policy thuật toán. Cần log class và **nguyên nhân (cause)** có redaction, xem `javax.net.debug=ssl,handshake` trong môi trường kiểm thử riêng khi cần; không bật debug TLS vô tội vạ ở production vì log có thể chứa metadata nhạy cảm.

### Connect timeout không phải deadline tổng

`setConnectTimeout(ms)` chủ yếu kiểm soát thời hạn chờ lập kết nối; `setReadTimeout(ms)` kiểm soát blocking read theo kỳ vọng `URLConnection`. Chúng **không thay thế** deadline cho toàn bộ workflow DNS/TLS/HTTP/parse/retry. Một response stream có thể nhỏ giọt dữ liệu đủ để mỗi read không timeout nhưng tổng thời gian cực lớn. Production cần giới hạn tổng thời gian/số bytes và hủy đúng lifecycle.

### Khi kết nối lỗi giữa POST/PUT, đừng retry mù

TLS/transport error sau khi bắt đầu gửi request không chứng minh server chưa thực hiện nghiệp vụ. Với POST thanh toán, phải dùng idempotency key/đối soát. Với GET/HEAD hoặc PUT/DELETE theo semantics idempotent, vẫn cần chính sách retry có budget, timeout và xác minh thực tế; đừng coi “dùng HTTPS” là đảm bảo exactly-once.

## 12. SAN, wildcard, IP và chứng chỉ khi triển khai qua nhiều môi trường

### Truy cập bằng DNS name đã phát hành

Ứng dụng yêu cầu `https://billing.internal.example`, certificate chứa `DNS:billing.internal.example`, trust path hợp lệ và TLS policy đúng → hostname validation có thể thành công.

### Truy cập trực tiếp bằng IP

`https://10.0.2.15` cần certificate có `iPAddress SAN=10.0.2.15` theo policy; một certificate chỉ có `DNS:billing.internal.example` không được tự chấp nhận chỉ vì DNS của tên này trả `10.0.2.15`.

Nếu có thể, **nên dùng DNS name ổn định** trong URL và cấu hình DNS/route hợp lệ; tránh gọi dịch vụ theo IP rồi sửa verifier để bỏ qua mismatch. Nếu bắt buộc dùng IP, cần phát hành certificate có IP SAN và kiểm thử.

### Wildcard certificate

Certificate như `DNS:*.example.com` có quy tắc matching hạn chế; không coi nó là phép bao mọi subdomain ở mọi độ sâu hoặc domain gốc. Kiểm tra tên cụ thể theo chuẩn/policy. Không viết regex `.*example.com` rồi tự thay JDK verifier.

### TLS termination / load balancer

Nếu client gọi `https://api.example.com` qua load balancer, certificate tại **TLS termination endpoint mà client thấy** phải phù hợp tên `api.example.com`. Certificate giữa load balancer và backend là một kết nối TLS khác với trust/hostname policy riêng. Chứng chỉ backend đúng không làm certificate frontend sai trở nên hợp lệ.

### SNI và nhiều certificate trên một IP

Server có thể chọn certificate dựa trên SNI của TLS ClientHello; client dùng IP literal thay hostname có thể ảnh hưởng SNI và khiến server trả certificate mặc định không đúng. **Không chẩn đoán mọi mismatch là lỗi truststore**: kiểm tra cả URL hostname, SNI, SAN, routing, certificate chain đang được peer trình bày và cấu hình proxy.

## 13. Custom HostnameVerifier, pinning và truststore rotation

### Hostname verifier không phải trust manager

`setHostnameVerifier(...)` thay đổi chính sách xác minh **tên máy trong TLS session** cho connection cụ thể; nó không phải API để import CA hoặc giải lỗi PKIX. `setSSLSocketFactory(...)` thay đổi TLS factory/trust/key configuration cho connection. Hai việc phải được cân nhắc độc lập.

| Mong muốn | Đường đi phù hợp | Không nên làm |
|---|---|---|
| Tin CA nội bộ | Thêm CA đúng vào truststore và dùng TrustManagerFactory | Verifier luôn true |
| Tin certificate self-signed trong lab | Import public cert vào truststore riêng | TrustManager bỏ mọi certificate check |
| Hostname không khớp SAN | Gọi đúng host hoặc cấp lại cert có SAN phù hợp | Tắt hostname verification |
| Triển khai mTLS | KeyManagerFactory cho client identity + TrustManagerFactory cho server trust | Copy private key server vào máy client |
| Chuyển certificate định kỳ | CA/rotation policy, truststore rollover, kiểm thử | Hardcode 1 fingerprint vĩnh viễn không có plan |
| TLS certificate pinning đặc biệt | Pin public key/certificate dưới review bảo mật và rotation | Regex CN hoặc bỏ PKIX kiểm tra |

### Certificate pinning không tự động giải quyết hostname

Pinning là policy ràng buộc certificate/public key với dịch vụ. Khi làm pinning, vẫn nên giữ **trust path và hostname verification** phù hợp, trừ khi thiết kế thay thế tương đương đã được chuyên gia kiểm chứng. Một cert/key được pin nhưng dùng cho host không đúng vẫn có thể vi phạm danh tính dịch vụ; hãy xem security architecture toàn phần.

### Rotation

Nếu CA nội bộ hoặc certificate được thay mới, truststore chứa certificate lá duy nhất có thể hết tác dụng; dùng trust CA phù hợp và chuẩn bị rollover nếu có thể. Đặt cảnh báo hết hạn, cập nhật trust material theo quy trình và test trước khi deployment. Không “chữa cháy” bằng cách bỏ xác minh chain/hostname.

### Password & secrets

Trong demo `changeit` là mật khẩu ví dụ công khai, **không có giá trị bảo vệ**. Trong production, lưu secret trong secret manager/keystore ACL, không log password, không hardcode source code, không commit private key. Dùng `char[]` khi API hỗ trợ và dọn bộ nhớ hợp lý, dù Java không đảm bảo loại bỏ mọi bản sao secret ngay lập tức.

## 14. Những điều về TLS mà SSLSocketFactory không tự giải quyết

Chọn một `SSLSocketFactory` hợp lệ là **điều kiện cấu hình**, không bảo đảm hệ thống vận hành an toàn trọn vẹn:

1. **Authorization**: một server HTTPS có certificate đúng vẫn có thể trả dữ liệu cho user sai nếu token/scopes không được kiểm tra.
2. **Cookie/session policy**: HTTPS không tự bảo đảm CSRF protection hoặc cookie Secure/HttpOnly/SameSite.
3. **Redirect policy**: HTTP redirect có thể dẫn sang host/scheme khác; client phải xét tràn credentials và trust mới.
4. **SSRF**: URL do user nhập có thể trỏ mạng nội bộ/metadata IP. HTTPS và truststore không thay URL allowlist, DNS/IP checks và egress firewall.
5. **Proxy**: kết nối HTTPS có thể đi qua HTTP CONNECT tunnel; proxy auth/routing không được SSLSocketFactory xử lý thay.
6. **Response validation**: TLS bảo vệ kênh và peer identity, không bảo đảm JSON theo schema, file an toàn hoặc nghiệp vụ thành công.
7. **HTTP status**: `200` không có nghĩa các side effect downstream đã hoàn tất; `202` có thể mới là accepted.
8. **Logging**: `javax.net.debug` và dump certificate/session có thể chứa metadata nhạy cảm; chỉ bật debug đủ thời gian cần thiết.
9. **Protocol policy**: `SSLContext.getInstance("TLS")` dùng các protocol do provider/JDK cho phép; hãy cập nhật JDK và chính sách vô hiệu thuật toán yếu.
10. **Connection pooling**: keep-alive/reuse có thể giữ socket hoặc session theo implementation; cập nhật policy không tự thu hồi tất cả connection đang dùng.

## 15. Sai lầm thường gặp: triệu chứng và cách sửa

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Tạo truststore rồi bỏ hostname verifier | Có thể chấp nhận certificate cho host khác | Giữ hostname verification mặc định |
| Viết TrustManager chấp nhận mọi cert | Dễ bị MITM vì không kiểm tra chain | Trust CA/cert cụ thể trong KeyStore |
| Verifier luôn trả `true` để “fix SSL” | Bỏ qua danh tính URL host | Sửa URL hoặc SAN certificate |
| Cho rằng đúng IP là đúng hostname | Nhiều host dùng một IP; khác reference identity | Match URL hostname/IP với SAN đúng loại |
| Tin chỉ CN=localhost là đủ | Bỏ qua SAN và quy tắc hiện đại | Phát hành SAN đúng và để JSSE kiểm tra |
| Gọi `https://127.0.0.1` với cert `DNS:localhost` | IP không khớp DNS SAN | Dùng localhost hoặc thêm IP SAN |
| Coi `getPeerPrincipal().getName()` là full verification | Subject CN không thay chain/SAN verification | Dùng JDK HTTPS default policy |
| Coi `SSLSocketFactory` là `HostnameVerifier` | Nhầm trust/transport với identity | Tách truststore và hostname check |
| Sửa `setDefaultSSLSocketFactory` toàn JVM | Ảnh hưởng connections khác không liên quan | Dùng `conn.setSSLSocketFactory` theo instance |
| Sửa `setDefaultHostnameVerifier` toàn JVM | Nguy cơ phá bảo mật nhiều thư viện | Không override global verifier |
| Cấu hình factory sau `getResponseCode()` | Connection đã khởi tạo, thiết lập quá muộn | Đặt trước connect/implicit connect |
| Ép `http://` URL thành HttpsURLConnection | `ClassCastException` | Kiểm tra scheme HTTPS |
| Cho rằng SSL handshake failure là HTTP 500 | Không có HTTP response khi TLS thất bại | Bắt `SSLException`/`IOException` riêng |
| Dùng `getInputStream` cho HTTP 4xx mà không xem error | Có thể nhận IOException, mất error body | `getResponseCode` + `getErrorStream` |
| Quên đóng response stream | Giữ tài nguyên/kết nối | `try-with-resources` + `disconnect` |
| Xem `disconnect` thay close stream | Có thể không giải phóng theo mong đợi | Đóng stream trước, disconnect trong finally |
| Gắn `Proxy.NO_PROXY` bừa vào production | Bypass egress policy | Dùng proxy/policy đã phê duyệt |
| Tin certificate self-signed ngoài lab không review | Trust giả, không có rotation | CA/PKI nội bộ có quản trị |
| Commit server keystore/private key | Lộ key cho attacker | Đặt ngoài source, ACL và secret manager |
| In password/Authorization trong log | Rò rỉ secrets | Redact và giới hạn diagnostics |
| Đặt timeout = 0 mà tưởng bị giới hạn | 0 thường biểu thị chờ vô hạn | Timeout dương và deadline tổng |
| Chỉ giới hạn connectTimeout | Read/TLS/logic khác còn có thể chờ | Đặt readTimeout và budget toàn workflow |
| Retry POST sau TLS/socket timeout vô điều kiện | Có thể tạo side effect trùng | Idempotency key/đối soát |
| Nghĩ factory mới tự reload truststore trên disk | Dùng trust material cũ | Quản lý lifecycle SSLContext/factory |
| Dùng chuỗi `"TLSv1.0"` để “tương thích” | Vô tình bật thuật toán cũ/yếu | Theo protocol policy JDK hiện hành |
| Nhầm chứng chỉ frontend/backend ở load balancer | Sửa sai truststore hoặc host | Kiểm tra TLS termination certificate đúng điểm |
| Đưa tên host từ query vào verifier | Host spoofing/SSRF/nhầm authority | Dựa trên URI đã kiểm soát và SAN checks |

## 16. Tình huống thực tế: phân biệt bốn nhóm lỗi gần giống nhau

### A. Lỗi PKIX chain

`javax.net.ssl.SSLHandshakeException` có cause liên quan `SunCertPathBuilderException` hoặc `ValidatorException`, ví dụ không có đường chứng chỉ được tin cậy. Kiểm tra server gửi chain đầy đủ, CA root/intermediate, truststore thật sự đang được dùng, certificate expiry và policy. **Không tắt hostname checking để sửa PKIX**.

### B. Hostname mismatch

Trust chain có thể hợp lệ nhưng lỗi liên quan URL hostname vs certificate SAN. Kiểm tra `new URL(...).getHost()`, certificate DNS/IP SAN, SNI và load balancer. Đừng cố sửa bằng cách import thêm chính certificate ấy vào truststore nếu vấn đề là **sai tên**.

### C. Kết nối bị từ chối

`ConnectException: Connection refused` xảy ra trước khi TLS handshake có thể thành công. Kiểm tra host/port/service binding, firewall, proxy/VPN. Sửa truststore không làm một TCP endpoint đang tắt bắt đầu lắng nghe.

### D. HTTP 403/404

Nếu TLS đã thành công, HTTP server có thể trả `403` hoặc `404` theo access policy/resource. Đây là kết quả HTTP, không phải chứng minh SSL config sai. Dùng `getResponseCode`/`getErrorStream` và application contract để xử lý; đừng retry hay đổi verifier vì status này.

**Debug có thứ tự:** URL scheme/host → DNS/IP/port/proxy → TLS certificate chain → hostname SAN → HTTP status/headers/body → business semantics. Cách này khoanh vùng đúng lớp thay vì thay mọi cấu hình SSL cùng lúc.

## 17. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Có thể dùng `HttpsURLConnection` với một truststore riêng mà không tắt hostname verification không?

**Đáp án:** Có. Tạo `SSLContext` từ `TrustManagerFactory` dùng truststore riêng, lấy `SSLSocketFactory` và gọi `conn.setSSLSocketFactory(factory)`. Giữ verifier mặc định.

**Câu 2.** Chứng chỉ có `DNS:localhost`, client dùng `https://127.0.0.1`. Vì sao có thể bị từ chối dù cả hai cùng trỏ loopback?

**Đáp án:** URL yêu cầu danh tính **IP** `127.0.0.1`, còn certificate chỉ khai báo **DNS SAN localhost**. Cùng địa chỉ mạng không làm hai reference identities bằng nhau.

**Câu 3.** Nếu muốn dùng URL `https://127.0.0.1` cho lab, cần gì?

**Đáp án:** Certificate có `iPAddress SAN=127.0.0.1`, trust path hợp lệ và TLS policy phù hợp. Không dùng verifier luôn true.

**Câu 4.** `TrustManagerFactory` và `HostnameVerifier` có cùng trách nhiệm?

**Đáp án:** Không. Trust manager kiểm tra certificate trust path/policy; hostname verification kiểm tra danh tính server có khớp URL host không. Cả hai đều cần thiết.

**Câu 5.** Gọi `conn.setSSLSocketFactory(...)` sau `conn.getResponseCode()` có hợp lệ không?

**Đáp án:** Không phải cách cấu hình đúng: `getResponseCode()` có thể đã thiết lập connection. Phải đặt factory trước khi bắt đầu kết nối.

**Câu 6.** `HttpsURLConnection.setDefaultSSLSocketFactory(...)` ảnh hưởng phạm vi nào?

**Đáp án:** Mặc định static cho các instance mới của lớp, không chỉ connection hiện tại. Trong thư viện dùng chung JVM nên tránh thay global, ưu tiên per-instance.

**Câu 7.** Vì sao ví dụ xuất `server.crt` rồi import vào `trust.p12` thay vì copy `server.p12` sang client?

**Đáp án:** `server.p12` chứa **private key server**, client chỉ cần **public certificate/CA trust** để xác minh; không được rò rỉ private key.

**Câu 8.** `getPeerPrincipal().getName()` chứa `CN=localhost`. Có chứng minh certificate match `https://localhost` không?

**Đáp án:** Không. Đây chỉ là subject information; xác minh hostname nên dựa trên SAN và policy của HTTPS verifier, kết hợp trust chain verification.

**Câu 9.** Khi TLS handshake thất bại, có chắc nhận HTTP `500` không?

**Đáp án:** Không. TLS thất bại có thể khiến client chưa có HTTP response hợp lệ; thường ném `SSLException` hoặc `IOException` với cause cụ thể.

**Câu 10.** Nếu server trả HTTP `404` sau TLS handshake thành công, nên chỉnh truststore không?

**Đáp án:** Không chỉ từ `404`. Đây là HTTP resource/status issue; kiểm tra URL path, quyền truy cập và response body qua API.

**Câu 11.** Có nên gọi `getInputStream()` cho mọi HTTP status để đọc JSON lỗi?

**Đáp án:** Không. Với HTTP error, `getInputStream()` có thể ném IOException; sau khi có response, xem `getResponseCode()` và `getErrorStream()` theo contract.

**Câu 12.** Certificate self-signed trong lab có làm hostname verification tự vô hiệu không?

**Đáp án:** Không. Nếu client tin certificate qua truststore riêng, URL host vẫn phải match danh tính certificate.

**Câu 13.** `SSLContext.getInstance("TLS")` có đồng nghĩa luôn dùng TLS 1.3 không?

**Đáp án:** Không. Provider/JDK và cấu hình chính sách quyết định protocol version được enable/negotiated. Giữ runtime và security policy cập nhật.

**Câu 14.** Có nên dùng `HostnameVerifier` always-true để tạm chạy test rồi quên gỡ không?

**Đáp án:** Không. Nó phá bảo đảm danh tính HTTPS và rất dễ lọt vào production. Dùng truststore thử nghiệm và certificate SAN đúng.

**Câu 15.** Khi dùng proxy HTTPS, TLS peer mà client cần xác minh là ai?

**Đáp án:** Với mô hình HTTP CONNECT tunnel thông thường và TLS end-to-end, client cần xác minh **origin hostname** mà nó yêu cầu, không thay bằng proxy hostname. Nếu có TLS interception được quản trị, trust/identity model phải được phân tích riêng.

**Câu 16.** `disconnect()` có thay việc đóng response InputStream không?

**Đáp án:** Không. Đóng stream bằng try-with-resources khi có thể, gọi disconnect trong finally để ứng dụng báo không còn dùng connection.

**Câu 17.** Tại sao demo cố ý tắt redirect bằng `setInstanceFollowRedirects(false)`?

**Đáp án:** Để hai request đến đúng hai URL được chọn trong bài, không bị redirect làm thay đổi hostname/scheme và lẫn lộn kết quả xác minh. Production cần redirect policy được kiểm soát.

**Câu 18.** Nếu đã import một cert vào truststore nhưng vẫn lỗi “No subject alternative names matching IP address”, làm gì?

**Đáp án:** Xác minh URL host/IP và certificate SAN; phát hành lại certificate có IP SAN đúng hoặc gọi đúng DNS name. Import truststore không giải quyết mismatch.

**Câu 19.** Có thể phân biệt expired cert với DNS failure chỉ từ HTTP statusCode không?

**Đáp án:** Không. Đây đều là lỗi xảy ra trước hoặc trong TLS/transport, có thể không có HTTP status. Phải xem exception class và cause.

**Câu 20.** Nếu có nhiều microservices nội bộ, nên thêm từng self-signed leaf cert vào app source code không?

**Đáp án:** Thường không. Ưu tiên PKI/CA nội bộ được quản trị, truststore cấu hình tập trung theo phạm vi cần thiết, rotation, secrets và monitoring; giữ hostname verification chuẩn.

## 18. Checklist triển khai HttpsURLConnection an toàn

Trước khi đưa Java HTTPS client vào sử dụng:

1. **URL phải là HTTPS** và hostname/IP đích được phép theo policy; không cast từ HTTP.
2. **Xác định nguồn trust**: mặc định của JVM, CA nội bộ được quản lý hay chứng chỉ demo riêng. Không dùng trust-all.
3. **Tạo SSLContext đúng** qua `KeyStore` và `TrustManagerFactory`; KeyManager chỉ khi cần client identity/mTLS.
4. **Gắn SSLSocketFactory per-instance** trước khi connect; tránh sửa global defaults trong library/SDK.
5. **Giữ hostname verification mặc định**, không có verifier luôn trả true.
6. **Certificate phải chứa SAN đúng**: DNS SAN cho DNS URL, iPAddress SAN cho IP URL; đừng dựa vào subject CN.
7. **Kiểm tra SNI/termination** khi triển khai qua load balancer hoặc nhiều host dùng chung IP.
8. **Cấu hình timeout dương** cho connect/read và **deadline tổng** ở tầng ứng dụng.
9. **Giữ redirects có kiểm soát**, kiểm tra URL/scheme/host của đích chuyển tiếp, không để rò credentials.
10. **Đọc HTTP response đúng**: status, headers, success input stream và error stream; tách network/TLS failure.
11. **Đóng InputStream/OutputStream**, gọi `disconnect()` khi xong, không gọi method TLS session đã hết lifecycle.
12. **Log an toàn**: exception class/cause phù hợp, hostname đã chuẩn hóa, không log private key/password/token.
13. **Giám sát certificate expiry và truststore rotation**, kiểm thử trước khi thay CA/cert.
14. **Kiểm thử positive và negative case**: cert hợp lệ đúng host phải qua; cert đáng tin sai host phải bị từ chối; cert chưa trusted phải bị từ chối.
15. **Thử IPv4/IPv6 và DNS/IP SAN** nếu client có thể truy cập host theo nhiều dạng.
16. **Với upload/payment POST**, xử lý retry/idempotency riêng; TLS không tự bảo đảm đúng một lần.
17. **Duy trì JDK security updates** và protocols/ciphers theo chính sách; không bật TLS/SSL cũ vì lỗi tương thích chưa điều tra.
18. **Tách bảo mật transport khỏi authorization và business validation**; cả ba đều quan trọng.

**Kết luận:** `HttpsURLConnection` dùng `SSLSocketFactory` để tạo TLS sockets và trust configuration phù hợp, nhưng **trust chain verification không thay thế hostname verification**. Trong Java 17, hãy giữ default HTTPS hostname checking, cấu hình CA/certificate tin cậy bằng truststore riêng khi cần, và chỉ xem kết nối là đúng server khi URL host khớp SAN đã xác minh. Demo cho thấy `localhost` được tin cậy và chấp nhận, nhưng `127.0.0.1` vẫn bị từ chối trên **cùng server** vì danh tính IP không có trong certificate.

### Tài liệu tham khảo

- [Java SE 17 — HttpsURLConnection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html)
- [Java SE 17 — SSLSocketFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocketFactory.html)
- [Java SE 17 — HostnameVerifier API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HostnameVerifier.html)
- [Java SE 17 — SSLContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [Java SE 17 — TrustManagerFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html)
- [Java SE 17 — KeyStore API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html)
- [Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525.html)
- [RFC 2818 — HTTP over TLS (bối cảnh lịch sử)](https://www.rfc-editor.org/rfc/rfc2818.html)