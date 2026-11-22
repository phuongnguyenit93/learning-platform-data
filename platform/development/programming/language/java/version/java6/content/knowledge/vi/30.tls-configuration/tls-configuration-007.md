# Trust manager, key manager và vai trò cấu hình chứng chỉ trong TLS (Java 17+)

## 1. Mục tiêu và mô hình tư duy

TLS không chỉ mã hóa bytes: một kết nối an toàn còn phải xác thực **đang kết nối với ai**. Trong Java Secure Socket Extension (**JSSE**), hai thành phần có tên rất giống nhau nhưng đảm nhiệm hai câu hỏi khác nhau:

- **`KeyManager`: “Tôi trình danh tính nào?”** Chọn certificate chain và private key của **chính tiến trình Java** để tham gia TLS handshake.
- **`TrustManager`: “Tôi có tin danh tính phía bên kia không?”** Kiểm tra certificate chain của **peer** có đáng tin theo trust anchors/chính sách hay không.

Hai nhà máy **`KeyManagerFactory`** và **`TrustManagerFactory`** tạo các manager tương ứng từ `KeyStore`/trust material. `SSLContext` sử dụng chúng để tạo TLS sockets/engines; `SSLParameters` bổ sung các quyết định cho kết nối cụ thể như endpoint hostname verification hoặc client authentication. Đây là các API chuẩn vẫn được hỗ trợ trong Java 17, 21 và các JDK hiện đại; không dùng cách tiếp cận legacy trust-all, TLS 1.0 hay chứng chỉ yếu.

**Sau bài, bạn có thể:** phân biệt keystore và truststore, cấu hình server-authenticated TLS/mTLS, dùng PKCS#12 với `keytool`, bật hostname verification cho raw `SSLSocket`, đọc và xác minh lỗi chứng chỉ, kiểm thử Java TLS client/server thật và thiết kế rotation/authorization an toàn.

## 2. KeyManager và TrustManager: đừng đảo vai trò

| Câu hỏi | Phía Java làm gì? | Thành phần | Material thường cần |
| --- | --- | --- | --- |
| Làm sao **server chứng minh mình là server**? | Chọn server certificate và dùng private key tương ứng trong handshake. | `KeyManager`, thường là `X509KeyManager`. | Server identity keystore có `PrivateKeyEntry` và certificate chain. |
| Làm sao **client tin đúng server**? | Kiểm tra server certificate/path tới CA/anchor được tin, sau đó kiểm tra tên server. | `TrustManager`/`X509TrustManager` và endpoint identification. | Client truststore hoặc trust mặc định đáng tin; SAN khớp hostname/IP. |
| Làm sao **client chứng minh danh tính trong mTLS**? | Chọn client certificate và private key khi server yêu cầu. | Client `KeyManager`. | Client identity keystore, private key và client cert chain. |
| Làm sao **server tin client certificate** trong mTLS? | Yêu cầu client certificate, rồi xác thực chain/mục đích. | Server `TrustManager` + `needClientAuth`. | Server truststore chứa CA/anchor phát client certs. |
| Client đã xác thực có được phép đọc/sửa tài nguyên nào? | Áp dụng business authorization theo identity/tenant/role. | Logic ứng dụng/gateway. | Principal, SAN/issuer, policy và tài nguyên cần bảo vệ. |

**KeyManager không có trách nhiệm tin cậy certificate peer**. **TrustManager không cung cấp private key để chứng minh danh tính của chính mình**. Một endpoint mTLS thường cần **cả hai**, trong khi một HTTPS client thông thường chỉ cần trust manager để xác minh server và **không nhất thiết có client certificate**.

### 2.1. HTTPS/TLS một chiều (server authentication)

```text
HTTPS client                                     HTTPS server
+----------------------------+                   +---------------------------+
| TrustManager               |                   | KeyManager                |
| Trusts selected CA/anchor  |                   | Server private key        |
| Checks server cert chain   |                   | Server certificate chain  |
| Checks hostname/IP via     |                   +---------------------------+
| endpoint identification    |                               |
+----------------------------+                               |
              | ------ ClientHello / TLS negotiation ------->|
              |<----- server certificate + proof of key -----|
              |  verify chain/validity/policy/SAN             |
              |<======= encrypted, authenticated traffic ====>|
```

Trong HTTPS công khai, một Java client thường dựa vào truststore/provider mặc định. Client **không cần sở hữu private key của server**, và server **không bao giờ gửi private key qua mạng**.

### 2.2. Mutual TLS (mTLS)

```text
mTLS client                                          mTLS server
  KeyManager: client identity                         KeyManager: server identity
  TrustManager: server CA/anchor                       TrustManager: client CA/anchor
          |                                                    |
          |------------- ClientHello ------------------------->|
          |<------------ server certificate + proof ----------|
          | Verify chain + server hostname                     |
          |<------------ CertificateRequest ------------------|
          |------------- client certificate + proof ---------->|
          |                                 Verify client cert |
          |<========== encrypted connection =================>|
          | Application authorization remains necessary        |
```

mTLS cần đồng thời: client có identity và private key, server có identity và private key, hai phía tin đúng issuer/anchor của nhau, và **server thật sự bật yêu cầu xác thực client**, ví dụ `SSLServerSocket.setNeedClientAuth(true)`. Chỉ tạo server trust manager **chưa** tự động kích hoạt mTLS bắt buộc.

## 3. Chứng chỉ X.509, private key và trust anchor

Một **X.509 certificate** chứa public key, subject, issuer, thời hạn (`NotBefore`/`NotAfter`), các extensions như **Subject Alternative Name (SAN)**, Extended Key Usage (EKU), Key Usage, Basic Constraints và chữ ký của issuer. Nó **không** chứa private key. Private key phải được giữ bí mật tại endpoint sở hữu identity.

**Identity keystore** thường có cấu trúc:

```text
server.p12
  alias = server
  entry type = PrivateKeyEntry
  private key = confidential
  certificate chain = server leaf + optional intermediates
```

**Truststore** thường có cấu trúc:

```text
client-trust.p12
  alias = trusted-server-ca
  entry type = trustedCertEntry
  public certificate = trusted CA/anchor (or explicit test leaf)
  private key = NONE
```

`KeyStore` là một API trừu tượng; file `PKCS12 (.p12)` có thể chứa private key entries, trusted cert entries và dữ liệu được hỗ trợ bởi provider. **Tên file không quyết định vai trò** — việc đưa store vào `KeyManagerFactory` hay `TrustManagerFactory` và loại entry mới quyết định cách JSSE sử dụng. Tuy có thể đọc hai loại material từ cùng một store, thực hành vận hành nên tách identity và trust để giảm quyền, tránh nhầm keys và dễ rotate.

### 3.1. Những nhầm lẫn nguy hiểm

- **Import `client.crt` vào truststore không tạo client identity**: certificate là public material, không có matching private key.
- **Export `server-cert.pem` không xuất private key**: `keytool -exportcert` xuất chứng chỉ public.
- **Keystore có server key không đồng nghĩa client đã tin server**: phía client cần chain/trust anchors của nó.
- **Truststore có CA của client không đồng nghĩa server đã yêu cầu client cert**: phải bật client authentication.
- **Certificate chain trusted không đồng nghĩa tên host/IP đúng**: cần endpoint identification.
- **Handshake mTLS thành công không đồng nghĩa mọi client có quyền ngang nhau**: vẫn cần authorization mapping.

### 3.2. Self-signed leaf trong lab và CA production

Để demo deterministic, có thể tạo self-signed **server leaf** và **client leaf**, rồi import certificate public của server vào client truststore và của client vào server truststore. Khi đó hai phía tin cậy đúng một certificate đã chọn, đủ cho bài học. **Không tự động dùng kiểu pin leaf này trong production**: certificate rotation, multi-tenant authorization và chính sách CA trở nên khó quản lý.

Trong production, thường dùng CA/PKI được quản trị, issuance với SAN/EKU đúng, certificate chain đủ intermediates, trust anchors có lifecycle rõ ràng, revocation/expiry monitoring, least-privilege và secret storage/HSM khi cần.

## 4. Các class JSSE và cách nối với nhau

### 4.1. KeyManagerFactory và X509KeyManager

`KeyManagerFactory` lấy identity material (private key + chain). Với Java 17+:

```java
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identityKeyStore, identityPassword);

KeyManager[] keyManagers = kmf.getKeyManagers();
```

**Snippet:** `identityKeyStore` là `KeyStore` đã load, `identityPassword` là `char[]` của key entry. `getDefaultAlgorithm()` chọn default algorithm theo Java provider/security properties thay vì hard-code provider name. `X509KeyManager` có trách nhiệm chọn server/client alias, certificate chain và private key tương ứng; `X509ExtendedKeyManager` mở rộng lựa chọn theo `SSLSocket`/`SSLEngine` context, hữu ích khi SNI và nhiều aliases cần xử lý có chủ đích.

Một keystore có nhiều `PrivateKeyEntry` có thể phục vụ nhiều domains/tenants, nhưng **không được giả định alias đầu tiên sẽ được chọn**. Key type, certificate issuer, signature schemes, TLS handshake context và SNI đều có thể ảnh hưởng. Kiểm thử đúng certificate được trình cho mỗi hostname.

### 4.2. TrustManagerFactory và X509TrustManager

`TrustManagerFactory` khởi tạo trust policy từ truststore/trusted cert entries:

```java
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

TrustManager[] trustManagers = tmf.getTrustManagers();
```

**Snippet:** `trustStore` đã load và chứa trust anchors; `X509TrustManager` kiểm tra server/client chains qua các methods `checkServerTrusted(...)`, `checkClientTrusted(...)`, `getAcceptedIssuers()`. `X509ExtendedTrustManager` bổ sung kiểm tra trong context TLS `Socket`/`SSLEngine`, đặc biệt quan trọng với endpoint identity và algorithm constraints.

Trust manager là thành phần xác thực **peer**, không gửi private key của chính ứng dụng. Không thay bằng một custom manager có method `checkServerTrusted` hoặc `checkClientTrusted` rỗng: đó là **trust-all**, có thể cho phép man-in-the-middle và spoofing.

### 4.3. SSLContext

`SSLContext` kết nối các managers và secure random:

```java
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, new SecureRandom());
```

`SSLContext` tạo `SSLSocketFactory`, `SSLServerSocketFactory` hoặc `SSLEngine`; giao thức TLS được đàm phán theo các versions/algorithms đang được provider/JDK/policy cho phép. Với Java hiện đại, vận hành an toàn xoay quanh **TLS 1.2 và TLS 1.3**, không kích hoạt SSLv3/TLS 1.0/1.1 hay cipher suites bị vô hiệu hóa chỉ để bỏ lỗi.

`SSLContext.init(null,null,...)` có ngữ nghĩa defaults của provider, **không phải cấu hình universal trust-all**. Đừng suy hệ điều hành nào cũng cung cấp cùng tập root CAs: Java truststore, vendor provider, container image và system properties có thể khác.

### 4.4. SSLParameters và xác thực endpoint

Một chain có thể đúng CA nhưng certificate thuộc `files.example.com`, không phải `payments.example.com`. Client kết nối tới tên sau **vẫn phải từ chối**. Với raw `SSLSocket` ở client mode, bật kiểm tra tên:

```java
SSLParameters params = client.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
client.setSSLParameters(params);
client.startHandshake();
```

Đây là snippet với `SSLSocket client` đã tạo; thứ tự quan trọng: phải cấu hình trước handshake. `SSLParameters` còn hỗ trợ protocols, cipher suites, SNI, algorithm constraints và client-auth flags. Với Java `HttpClient`/`HttpsURLConnection` dùng HTTPS bình thường, endpoint verification thuộc HTTP/TLS stack; **đừng tắt cơ chế đó để qua lỗi chứng chỉ**.

### 4.5. SSLServerSocket và SSLSession

Server TLS bật mTLS bắt buộc bằng:

```java
SSLServerSocket server = /* initialized TLS server socket */;
server.setNeedClientAuth(true); // Require valid client certificate
```

**Snippet:** code đầy đủ khởi tạo server socket qua `serverContext.getServerSocketFactory()`. Khác biệt:
- `setWantClientAuth(true)`: server **đề nghị** client cert; kết nối có thể tiếp tục khi client không cung cấp cert.
- `setNeedClientAuth(true)`: server **yêu cầu** client auth; thiếu identity/certificate phù hợp khiến handshake không thành công.

Sau handshake, `SSLSession.getPeerPrincipal()`/`getPeerCertificates()` có thể cung cấp thông tin identity đã được TLS xác thực. Ứng dụng vẫn phải mapping identity sang quyền truy cập đúng tenant/resource; không lấy HTTP header tự khai báo `X-Client-Cert` từ request chưa được proxy tin cậy làm bằng chứng mTLS.

## 5. Trust chain, hostname/SAN, EKU và certificate validation

### 5.1. Trust chain != endpoint name

Một chứng chỉ do CA trusted ký nhưng SAN chỉ cho `files.example.com` **không được phép** dùng để xác thực `payments.example.com`. Khi client kết nối bằng **IP literal** `127.0.0.1`, certificate phải có SAN dạng **IP Address:127.0.0.1**, không phải chỉ `CN=localhost`.

Lab sử dụng:

```text
Server subject: CN=localhost
SAN:
  DNS:localhost
  IP Address:127.0.0.1
Extended Key Usage: serverAuth

Client subject: CN=demo-client
Extended Key Usage: clientAuth
```

**SNI** giúp server lựa chọn certificate khi có nhiều names trên cùng endpoint; SNI không thay thế hostname verification và không tự xác thực caller. Dùng `X509ExtendedKeyManager` nếu policy chọn alias theo context phức tạp; không viết tùy biến để bỏ qua certificate usages.

### 5.2. Thời hạn, mục đích và chính sách mật mã

Trong validation:
- Kiểm tra certificate còn hạn hiệu lực; NTP/đồng hồ sai có thể làm certificate `not yet valid` hoặc `expired`.
- EKU `serverAuth`/`clientAuth` phải phù hợp nhiệm vụ.
- Key Usage và Basic Constraints/CA flags phải phù hợp.
- Chain phải dẫn tới trust anchor có chủ đích theo policy; thiếu intermediate có thể gây `PKIX path building failed`.
- Disabled algorithms/key sizes yếu có thể bị provider/JDK từ chối dù anchor được import.
- Revocation qua CRL/OCSP **không được giả định tự động hoạt động ở mọi môi trường**; nếu compliance yêu cầu, cấu hình PKIX/JSSE/enterprise policy và test lỗi mạng/timeout/responder cụ thể.

### 5.3. Truststore mặc định và explicit truststore

Với public HTTPS, client thường dùng trust material mặc định được quản trị bởi JVM/provider. Khi cần xem defaults qua factory:

```java
TrustManagerFactory factory = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
factory.init((KeyStore) null);
TrustManager[] defaults = factory.getTrustManagers();
```

**Snippet:** `null` ở đây yêu cầu provider chọn **default trust material**, không đồng nghĩa tin mọi certificate. Các properties liên quan thường gặp:
- `javax.net.ssl.trustStore`, `javax.net.ssl.trustStorePassword`, `javax.net.ssl.trustStoreType`.
- `javax.net.ssl.keyStore`, `javax.net.ssl.keyStorePassword`, `javax.net.ssl.keyStoreType`.

**Global system properties ảnh hưởng JVM process** và có thể tác động nhiều clients. Với nhiều upstreams hoặc private CAs, ưu tiên tạo `SSLContext` riêng cho đúng client/service khi framework hỗ trợ. Thay truststore file trên disk **không khiến SSLContext đã tạo tự tải lại**; cần lifecycle reload và rollout kiểm thử.

## 6. Sơ đồ chứng chỉ cho ba tình huống

| Tình huống | Client KeyManager | Client TrustManager | Server KeyManager | Server TrustManager |
| --- | --- | --- | --- | --- |
| Public HTTPS server auth | Thường không cần client identity. | Tin CA server và kiểm tra SAN hostname. | Trình server private key/cert chain. | Không dùng để xác thực client cert nếu không yêu cầu mTLS. |
| Private server HTTPS với private CA | Không cần nếu không mTLS. | Tin private CA server, kiểm tra SAN. | Server identity từ private PKI. | Chỉ cần khi có client auth. |
| mTLS service-to-service | Client private key/cert chain. | Tin server CA + hostname verification. | Server private key/cert chain. | Tin client CA và bắt buộc client auth. |

**Một server có truststore của CA client nhưng chưa gọi `setNeedClientAuth(true)` không thể kết luận mTLS đang được thực thi.** Ngược lại, client đưa certificate vào `client-trust.p12` không giúp client chứng minh sở hữu private key; phải có `PrivateKeyEntry` trong identity store hoặc provider như HSM.

## 7. Lab PKCS#12 với keytool: tự tạo keystore/truststore

Tạo thư mục mới `tls-lab`, sử dụng **JDK 17+** có `keytool`, `javac`, `java` trên PATH. Bốn files cần tạo:
1. `server.p12`: identity server, self-signed leaf, private key RSA 3072, SAN DNS localhost + IP 127.0.0.1, EKU serverAuth.
2. `client.p12`: identity client, self-signed leaf, private key RSA 3072, EKU clientAuth.
3. `client-trust.p12`: public server certificate được client chủ đích tin.
4. `server-trust.p12`: public client certificate được server chủ đích tin.

### 7.1. Lệnh PowerShell đã kiểm chứng

```powershell
New-Item -ItemType Directory -Path tls-lab -Force | Out-Null
Set-Location tls-lab
$pass = "changeit"

keytool -genkeypair -alias server -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 30 -dname "CN=localhost, OU=Demo, O=Training, C=VN" -ext "SAN=dns:localhost,ip:127.0.0.1" -ext "EKU=serverAuth" -storetype PKCS12 -keystore server.p12 -storepass $pass -keypass $pass -noprompt
keytool -genkeypair -alias client -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 30 -dname "CN=demo-client, OU=Demo, O=Training, C=VN" -ext "EKU=clientAuth" -storetype PKCS12 -keystore client.p12 -storepass $pass -keypass $pass -noprompt

keytool -exportcert -rfc -alias server -keystore server.p12 -storepass $pass -file server-cert.pem
keytool -exportcert -rfc -alias client -keystore client.p12 -storepass $pass -file client-cert.pem

keytool -importcert -alias trusted-server -file server-cert.pem -keystore client-trust.p12 -storetype PKCS12 -storepass $pass -noprompt
keytool -importcert -alias trusted-client -file client-cert.pem -keystore server-trust.p12 -storetype PKCS12 -storepass $pass -noprompt
```

Các lệnh PowerShell trên viết một dòng cho từng `keytool` command để tránh khác biệt continuation syntax giữa shells; trên bash/zsh có thể dùng cùng tham số `keytool` nhưng cú pháp gán biến khác. **`changeit` chỉ là mật khẩu demo tạm thời**; không được dùng production hoặc commit private keys vào repository. Lệnh với `-storepass` có thể lộ trong command history/process list, nên production cần secret manager/credentials tooling được phê duyệt.

### 7.2. Kiểm tra public cert và private key entry

```powershell
keytool -list -v -keystore server.p12 -storepass $pass
keytool -list -v -keystore client.p12 -storepass $pass
keytool -list -v -keystore client-trust.p12 -storepass $pass
keytool -list -v -keystore server-trust.p12 -storepass $pass
```

Đối chiếu:
- `server.p12`, `client.p12` có `PrivateKeyEntry` và certificate chain.
- `client-trust.p12` và `server-trust.p12` có `trustedCertEntry`, **không** có peer private key.
- Certificate server có SAN IP:127.0.0.1 và DNS:localhost; EKU `serverAuth`.
- Certificate client có EKU `clientAuth`.
- Các certificate nằm trong thời hạn 30 ngày từ lúc tạo.

**Giới hạn lab:** import self-signed **leaf** làm trust anchor trực tiếp để kiểm thử, không thay thế CA production/issuance, intermediate chains, rotation hay revocation policy. Với production thường tin CA đã xác minh out-of-band và có quy trình cấp/thu hồi/đổi khóa.

## 8. Chương trình Java 17+ chạy thực tế: TlsManagersDemo.java

### 8.1. Thiết kế kiểm thử

Chương trình sau:
- Load bốn stores PKCS12.
- Khởi tạo `KeyManagerFactory` và `TrustManagerFactory` riêng cho hai phía.
- Tạo hai `SSLContext` (server/client).
- Server bind **127.0.0.1:0** (OS cấp port ngẫu nhiên), yêu cầu client certificate qua `setNeedClientAuth(true)`.
- Client `SSLSocket` bật `HTTPS endpoint identification`, kết nối bằng **IP 127.0.0.1** (khớp SAN IP), bắt tay.
- Hai phía đọc `SSLSession.getPeerPrincipal()` sau handshake và echo bytes `HELLO`.
- Test âm: tạo client với **sai truststore** (chỉ tin client leaf, không tin server leaf), xác nhận server certificate bị từ chối ở handshake.
- In **9 dòng stdout cố định** và kết thúc, không in certificates/private keys/password/negotiated cipher.
- Đóng sockets/executor bằng try-with-resources/finally.

### 8.2. Toàn bộ file TlsManagersDemo.java

```java
import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509KeyManager;
import javax.net.ssl.X509TrustManager;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class TlsManagersDemo {

    private static KeyStore loadStore(Path path, char[] password)
            throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            store.load(in, password);
        }
        return store;
    }

    private static KeyManager[] keyManagers(
            Path identityStore, char[] password) throws Exception {
        KeyManagerFactory factory = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        factory.init(loadStore(identityStore, password), password);
        return factory.getKeyManagers();
    }

    private static TrustManager[] trustManagers(
            Path trustStore, char[] password) throws Exception {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(loadStore(trustStore, password));
        return factory.getTrustManagers();
    }

    private static SSLContext context(
            KeyManager[] keys, TrustManager[] trusts) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keys, trusts, new SecureRandom());
        return context;
    }

    private static SSLSocket connect(SSLContext context, int port)
            throws Exception {
        SSLSocket client = (SSLSocket) context.getSocketFactory()
                .createSocket("127.0.0.1", port);
        client.setSoTimeout(8000);
        SSLParameters params = client.getSSLParameters();
        params.setEndpointIdentificationAlgorithm("HTTPS");
        client.setSSLParameters(params);
        return client;
    }

    private record Result(boolean clientSawServer,
                          boolean serverSawClient,
                          boolean echoMatches) {}

    private static Result runMutualTls(
            SSLContext serverContext, SSLContext clientContext)
            throws Exception {
        try (SSLServerSocket server = (SSLServerSocket) serverContext
                .getServerSocketFactory().createServerSocket(
                        0, 10, InetAddress.getByName("127.0.0.1"))) {
            server.setNeedClientAuth(true);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<Boolean> sawClient = executor.submit(() -> {
                    try (SSLSocket incoming =
                                 (SSLSocket) server.accept()) {
                        incoming.setSoTimeout(8000);
                        incoming.startHandshake();
                        boolean peerPresent = incoming.getSession()
                                .getPeerPrincipal() != null;
                        byte[] message = incoming.getInputStream().readNBytes(5);
                        incoming.getOutputStream().write(message);
                        incoming.getOutputStream().flush();
                        return peerPresent;
                    }
                });
                try (SSLSocket client =
                             connect(clientContext, server.getLocalPort())) {
                    client.startHandshake();
                    boolean sawServer = client.getSession()
                            .getPeerPrincipal() != null;
                    byte[] sent = "HELLO".getBytes(StandardCharsets.US_ASCII);
                    client.getOutputStream().write(sent);
                    client.getOutputStream().flush();
                    byte[] reply = client.getInputStream().readNBytes(5);
                    boolean ok = Arrays.equals(sent, reply);
                    return new Result(sawServer, sawClient.get(
                            10, TimeUnit.SECONDS), ok);
                }
            } finally {
                executor.shutdownNow();
            }
        }
    }

    private static boolean rejectsUntrustedServer(
            SSLContext serverContext, SSLContext wrongClientContext)
            throws Exception {
        try (SSLServerSocket server = (SSLServerSocket) serverContext
                .getServerSocketFactory().createServerSocket(
                        0, 10, InetAddress.getByName("127.0.0.1"))) {
            server.setNeedClientAuth(false);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<?> serverTask = executor.submit(() -> {
                    try (SSLSocket incoming =
                                 (SSLSocket) server.accept()) {
                        incoming.setSoTimeout(8000);
                        incoming.startHandshake();
                    } catch (IOException expectedForRejectedClient) {
                        // Client rejects server; server may see a TLS alert.
                    }
                });
                boolean rejected = false;
                try (SSLSocket client = connect(
                        wrongClientContext, server.getLocalPort())) {
                    try {
                        client.startHandshake();
                    } catch (SSLHandshakeException expected) {
                        rejected = true;
                    }
                }
                serverTask.get(10, TimeUnit.SECONDS);
                return rejected;
            } finally {
                executor.shutdownNow();
            }
        }
    }

    private static void check(boolean value, String label) {
        if (!value) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "Usage: java TlsManagersDemo server.p12 client.p12 "
                    + "client-trust.p12 server-trust.p12");
        }
        String secret = System.getenv("DEMO_STORE_PASS");
        if (secret == null || secret.isBlank()) {
            throw new IllegalStateException("Missing DEMO_STORE_PASS");
        }
        char[] password = secret.toCharArray();
        try {
            KeyManager[] serverKeys = keyManagers(
                    Path.of(args[0]), password);
            TrustManager[] serverTrust = trustManagers(
                    Path.of(args[3]), password);
            KeyManager[] clientKeys = keyManagers(
                    Path.of(args[1]), password);
            TrustManager[] clientTrust = trustManagers(
                    Path.of(args[2]), password);

            boolean hasServerKeys = Arrays.stream(serverKeys)
                    .anyMatch(k -> k instanceof X509KeyManager);
            boolean hasServerTrust = Arrays.stream(serverTrust)
                    .anyMatch(t -> t instanceof X509TrustManager);
            boolean hasClientKeys = Arrays.stream(clientKeys)
                    .anyMatch(k -> k instanceof X509KeyManager);
            boolean hasClientTrust = Arrays.stream(clientTrust)
                    .anyMatch(t -> t instanceof X509TrustManager);
            check(hasServerKeys && hasServerTrust && hasClientKeys
                    && hasClientTrust, "JSSE manager configuration");

            SSLContext serverContext = context(serverKeys, serverTrust);
            SSLContext clientContext = context(clientKeys, clientTrust);

            Result result = runMutualTls(serverContext, clientContext);
            check(result.clientSawServer && result.serverSawClient
                    && result.echoMatches, "mutual TLS exchange");

            SSLContext wrongClient = context(clientKeys, serverTrust);
            boolean rejected = rejectsUntrustedServer(
                    serverContext, wrongClient);
            check(rejected, "untrusted server must fail");

            System.out.println("serverKeyManagerLoaded="
                    + hasServerKeys);
            System.out.println("serverTrustManagerLoaded="
                    + hasServerTrust);
            System.out.println("clientKeyManagerLoaded="
                    + hasClientKeys);
            System.out.println("clientTrustManagerLoaded="
                    + hasClientTrust);
            System.out.println("mutualTlsHandshake=true");
            System.out.println("serverSawClientCertificate="
                    + result.serverSawClient);
            System.out.println("clientSawServerCertificate="
                    + result.clientSawServer);
            System.out.println("messageRoundTrip="
                    + result.echoMatches);
            System.out.println("untrustedServerRejected="
                    + rejected);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

### 8.3. Biên dịch, chạy và giải thích

Sau khi lưu file `TlsManagersDemo.java` cùng thư mục với 4 PKCS#12 stores:

```powershell
javac --release 17 -encoding UTF-8 TlsManagersDemo.java
$env:DEMO_STORE_PASS = "changeit"
java TlsManagersDemo server.p12 client.p12 client-trust.p12 server-trust.p12
Remove-Item Env:\DEMO_STORE_PASS
```

Chương trình dùng `KeyManagerFactory.getDefaultAlgorithm()` và `TrustManagerFactory.getDefaultAlgorithm()`, không hard-code provider name. `SSLContext.getInstance("TLS")` cho provider chọn protocols đang allowed; `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` làm raw SSLSocket xác thực đúng **IP literal 127.0.0.1** trong SAN server certificate.

Server bắt buộc client cert. Trong test âm, `wrongClient` dùng `serverTrust` làm trust của **client**: store đó chỉ tin **client leaf**, không có server leaf, nên bắt tay server-auth phải bị từ chối. Không sửa trust manager thành accept-all, không tắt hostname verification và không cho phép fallback tới insecure TLS.

**Stdout 9 dòng đã được kiểm chứng khi biên dịch với `javac --release 17` và chạy trên JDK hiện đại:**

```text
serverKeyManagerLoaded=true
serverTrustManagerLoaded=true
clientKeyManagerLoaded=true
clientTrustManagerLoaded=true
mutualTlsHandshake=true
serverSawClientCertificate=true
clientSawServerCertificate=true
messageRoundTrip=true
untrustedServerRejected=true
```

Ý nghĩa:
1. Hai phía đã có KeyManager/TrustManager dạng X.509.
2. **`mutualTlsHandshake=true`**: mTLS handshake thành công với server `needClientAuth`.
3. **`serverSawClientCertificate=true`**: phía server có peer principal sau khi xác thực client.
4. **`clientSawServerCertificate=true`**: phía client có peer principal từ server cert phù hợp trust/SAN.
5. **`messageRoundTrip=true`**: bytes `HELLO` được trao đổi thực qua TLS socket, không chỉ khởi tạo `SSLContext`.
6. **`untrustedServerRejected=true`**: sai truststore thực sự chặn handshake.

Test đã thực thi trên loopback, không gửi traffic tới website ngoài. Cổng TCP ngẫu nhiên, cipher suite được negotiation và protocol version cụ thể **không** được in vì sẽ phụ thuộc provider/JDK/OS. Đây là TLS transport example, không triển khai HTTP routing.

## 9. HTTP client và server trong ứng dụng thực

### 9.1. Java HttpClient với SSLContext riêng

```java
SSLContext tls = /* cấu hình KeyManagers/TrustManagers đúng */;
HttpClient client = HttpClient.newBuilder()
        .sslContext(tls)
        .connectTimeout(Duration.ofSeconds(10))
        .build();
```

**Snippet:** cần `javax.net.ssl.SSLContext`, `java.net.http.HttpClient`, `java.time.Duration`; `tls` đã được tạo từ factories. `HttpClient.Builder.sslContext(...)` cho phép cấu hình TLS theo từng client thay vì thay global truststore cho toàn JVM. Với mTLS, client context cần **cả KeyManager identity và TrustManager cho server**. Với public HTTPS thông thường, có thể dùng default HTTPS client/trust và không cần client key manager.

### 9.2. HTTPS server

Một HTTPS server hoặc framework yêu cầu server identity material (private key + chain) qua key manager. Nếu muốn mTLS, cấu hình thêm server trust manager tin client CA và bật **required client authentication**. Không chỉ đưa client cert vào file keystore server rồi tin rằng server tự yêu cầu mTLS.

Server side app phải:
- Đọc peer identity sau successful handshake.
- Map SAN/issuer/cert identity tới service account/tenant và phân quyền theo resource.
- Có TLS protocol/algorithm constraints phù hợp deployment.
- Quản lý CA trust, certificate renewal, expiry alerts và graceful reload.
- Không log private keys/passwords; không expose `.p12` qua static file endpoints.

### 9.3. Multi-tenant, SNI và nhiều aliases

Khi server có nhiều DNS identities:
- SNI và JSSE key selection quyết định certificate được trình.
- Client vẫn phải verify SAN của tên server đang gọi.
- Một `KeyManager` mặc định có thể chọn đúng alias theo handshake, nhưng cần integration test với nhiều tên/certs.
- Nếu cần custom alias policy, cân nhắc `X509ExtendedKeyManager` với kiểm thử và delegation đầy đủ, không hard-code alias đầu tiên.
- Tách trust policies khi các tenants có CA/đối tác khác nhau để tránh **trust rộng hơn mức cần thiết**.

## 10. Failure modes và troubleshooting

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý an toàn |
| --- | --- | --- |
| `PKIX path building failed` / `unable to find valid certification path` | Không có CA/anchor phù hợp, thiếu intermediate, sai truststore. | Xác minh chain/CA từ nguồn tin cậy, sửa truststore, không trust-all. |
| `No subject alternative names present` / `No name matching ...` | Server certificate không có SAN khớp hostname/IP. | Cấp chứng chỉ đúng SAN hoặc gọi đúng DNS name. |
| `Received fatal alert: certificate_required` / mTLS fail | Server cần client cert nhưng client không có key/cert hoặc không chọn được alias. | Kiểm tra PrivateKeyEntry, client EKU, KeyManager và trust issuer. |
| `certificate_unknown` / `bad_certificate` | Peer từ chối chain, validity, usage hoặc algorithm. | So logs server/client, certs, EKU, trust manager, provider policy. |
| `UnrecoverableKeyException` | Sai password private key entry. | Sửa key password/credential source, không log password. |
| `Keystore was tampered with, or password was incorrect` | Store file/type/password không đúng. | Kiểm tra đường dẫn, PKCS12, file integrity/permissions. |
| `handshake_failure` / `no cipher suites in common` | Phiên bản TLS/cipher/signature scheme/key type/algorithm constraints không tương thích. | So phiên bản JDK/security policies, không bật lại protocols yếu. |
| Certificate expired/not yet valid | Validity interval hoặc đồng hồ hệ thống sai. | Renew certificate, kiểm tra NTP và expiry alerts. |
| Certificate chain accepted nhưng request trả 403 | TLS authenticates identity nhưng app authorization từ chối. | Kiểm tra role/tenant/SAN mapping trong app. |
| Truststore đã thay nhưng kết nối vẫn dùng cấu hình cũ | SSLContext/managers được tạo từ state trước khi reload. | Xây SSLContext mới, rollout/rotate theo lifecycle. |
| Port HTTPS chạy nhưng client không verify name | Raw SSLSocket thiếu endpoint identification. | Đặt `setEndpointIdentificationAlgorithm("HTTPS")` trước handshake. |

**Quy trình chẩn đoán**: xác minh server trình certificate nào → trust anchors phía client → chain/validity/EKU → SAN hostname/IP → TLS versions/ciphers → mTLS needClientAuth → client key manager → server truststore → app authorization. Đừng xử lý một lỗi chứng chỉ bằng cách vô hiệu hóa cả trust verification lẫn hostname verification.

Trong môi trường kiểm thử có phân quyền, có thể bật JSSE debug:

```bash
java -Djavax.net.debug=ssl,handshake TlsManagersDemo server.p12 client.p12 client-trust.p12 server-trust.p12
```

**Lệnh minh họa**, không phải output đã chạy. Cần mật khẩu trong `DEMO_STORE_PASS`. Debug logs có thể chứa certificate identities, hostnames, session metadata và chi tiết nhạy cảm; không đưa raw logs vào nơi công khai.

## 11. Những vấn đề vận hành hiện đại

### 11.1. Truststore không phải “danh sách tất cả cert từng thấy”

Một certificate được peer gửi tới **không tự động trở thành trusted**. Import không xác minh nguồn có thể khiến client tin attacker. Trong production, quản lý trusted CA/anchors theo chính sách, thay đổi có review và audit; không import theo kiểu “copy chain từ website không tin rồi thử lại”.

### 11.2. Rotation và keystore reload

- Private key và certificate có hạn sử dụng; chủ động renew trước expiry.
- Trong mTLS, đổi client cert/CA đòi kế hoạch phân phối identity/trust đồng bộ giữa hai phía.
- Giữ backup trust anchors/certs trong giai đoạn migration theo policy, sau đó thu hồi/remove cũ.
- Thay file `.p12` trên disk không bảo đảm `SSLContext` cũ tự cập nhật; tái tạo factories/context và chuyển connection lifecycle.
- Giám sát handshake failures sau rotation; không rollback sang trust-all.

### 11.3. Private keys và password handling

- Lưu secrets trong secret manager/KMS hoặc HSM/PKCS#11 provider khi cần.
- Hạn chế quyền file cho service account.
- Không dùng password `changeit`, private keys test, self-signed test certs trong production.
- Không commit key material trong Git hoặc đính kèm bug reports.
- `char[]` có thể xóa sau khi dùng, nhưng `System.getenv` trả `String` immutable nên demo **không** đạt chuẩn secret hygiene cao nhất; môi trường thật dùng secure credentials interfaces.
- Command-line `-storepass` có thể bị ghi history/process list; dùng tooling doanh nghiệp để nhập mật khẩu không lộ.

### 11.4. Revocation và certificate policies

Đừng khẳng định mọi Java TrustManager đều mặc định kiểm tra OCSP/CRL online. Nếu cần tuân thủ revocation, thiết kế `PKIX` revocation checker/CRL/OCSP theo provider và quy định, kiểm tra cả case offline/timeout. Certificate validation còn bao gồm key usage/EKU, algorithm constraints, SAN identity và chain/trust anchors; mỗi lớp phải được test đúng.

### 11.5. TLS 1.2, TLS 1.3 và provider differences

TLS 1.2/1.3 là nền tảng hiện đại; provider hỗ trợ và enabled cipher suites có thể khác giữa JDK vendors/FIPS/container image. Không hard-code "TLS 1.3 luôn negotiated" hoặc một cipher cụ thể trong output bài tập; để runtime chọn theo policy, rồi theo dõi protocol/cipher và thử interop thực tế. SSLv3, TLS1.0/1.1, MD5/SHA1 cho chứng chỉ mới hoặc keys quá yếu không nên được bật lại như mẹo tương thích.

## 12. Ma trận kiểm thử và bài tập

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Server-auth with trusted server CA/cert + đúng SAN | Handshake thành công. |
| mTLS with cả hai identity/trust và `needClientAuth` | Cả server/client thấy peer certificate, truyền dữ liệu thành công. |
| Client dùng sai truststore | Server certificate bị từ chối. |
| Server dùng sai client truststore | Client certificate bị từ chối. |
| mTLS client chỉ có cert public, không có matching private key | Không thể chứng minh identity. |
| Server chỉ `wantClientAuth`, client không có cert | Có thể tiếp tục mà không có client identity; không đủ cho bắt buộc mTLS. |
| Server cert thiếu SAN IP nhưng client gọi 127.0.0.1 | Endpoint identification từ chối. |
| Server cert hết hạn/chưa có hiệu lực | Validation thất bại. |
| Client cert có EKU không phù hợp | Client auth bị từ chối theo policy/provider. |
| Sai keystore password | Load/KeyManagerFactory init lỗi, không fallback trust-all. |
| Certificates có chain thiếu intermediate | PKIX validation có thể thất bại. |
| Rotate truststore nhưng không reload SSLContext | Connections mới có thể vẫn dùng material cũ. |
| CA tin được nhưng principal không có quyền resource | Application authorization phải từ chối. |
| JDK nâng cấp và algorithm disabled | Handshake có thể thất bại; cần cập nhật cert/cipher policy thay vì hạ security. |
| Debug log chứa secret/private key | Bảo vệ/redact; không đưa vào public CI. |

**Bài tập 1:** Viết một test server-auth only bỏ yêu cầu client cert, client không có identity key nhưng tin server CA; kiểm tra server authentication và endpoint SAN.

**Bài tập 2:** Bật `setNeedClientAuth(true)` nhưng xóa client key manager, assert handshake bị từ chối; chú ý TLS 1.3 có thể báo alert ở phía client trong bước I/O sau handshake, nên kiểm tra cả server.

**Bài tập 3:** Tạo server certificate chỉ có SAN `DNS:localhost` nhưng raw client kết nối `127.0.0.1`; assert từ chối vì thiếu `IP:127.0.0.1`, không tắt endpoint check.

**Bài tập 4:** Tạo một private test CA, cấp server/client cert và import **CA cert** vào truststores; đổi leaf certificate mà không phải import từng leaf.

**Bài tập 5:** Tạo hai mTLS client certificates khác nhau được cùng CA ký, nhưng chỉ một principal được phép gọi endpoint nhạy cảm; xác minh application authorization hoạt động.

**Bài tập 6:** Thêm nhiều cert aliases/SNI, kiểm tra server chọn cert có SAN phù hợp từng tên; nếu custom KeyManager, phải delegate các hành vi khác đúng JSSE contract.

**Bài tập 7:** Thực hành truststore rotation và recreate `SSLContext` trong controlled integration test; chứng minh kết nối trước/sau không bị lẫn các trust policies.

**Bài tập 8:** Thử certificate hết hạn, sai EKU, thiếu intermediate, key password sai; kiểm tra error message mà không bật trust-all.

**Bài tập 9:** Ghi nhận protocol/cipher đã đàm phán trong phép thử nhưng tránh đưa vào deterministic stdout kỳ vọng trên mọi provider.

**Bài tập 10:** Đọc tài liệu revocation và cấu hình test CA/OCSP hoặc CRL theo chính sách doanh nghiệp; xác minh cả trường hợp responder unavailable.

## 13. FAQ

**1. KeyManager và TrustManager có khác nhau chỉ ở tên gọi?** Không. KeyManager chọn identity/private key **của mình**, TrustManager kiểm tra identity/certificate **của peer**.

**2. HTTPS server cần gì?** Server KeyManager có private key/cert chain. Khi cần mTLS, server còn có TrustManager và bật required client auth.

**3. Java HTTPS client công cộng có phải luôn có client keystore?** Không. Client thường chỉ verify server certificate qua trust mặc định, không gửi client certificate trừ khi mTLS được yêu cầu.

**4. Chỉ có client.crt thì có thể thiết lập mTLS client không?** Không, cần matching private key hoặc provider/HSM có khả năng ký với khóa tương ứng và KeyManager phù hợp.

**5. TrustManager có tự kiểm tra hostname không?** Phải kiểm tra endpoint identification của **TLS client stack**; với raw SSLSocket dùng `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` trước handshake.

**6. Vì sao CN=localhost chưa đủ khi kết nối IP 127.0.0.1?** Tên đích là IP literal, cần SAN loại IP chính xác.

**7. Có thể đặt cả identity certificate và CA vào một PKCS12 không?** Về mặt cấu trúc có thể; nhưng phải hiểu loại entries và cách factories dùng chúng. Production thường tách identity và trust theo ownership.

**8. Tại sao demo import self-signed leaf?** Để deterministic lab không cần CA infrastructure; production thường trust CA có kiểm soát và quy trình rotation/revocation.

**9. Truststore cần chứa private key không?** Không. Trust anchors là public certificates; private key của peer không bao giờ được chia sẻ.

**10. Chỉ đặt server TrustManager đã là mTLS?** Chưa. Cần yêu cầu client cert qua `needClientAuth` và client phải có KeyManager identity.

**11. `setWantClientAuth(true)` và `setNeedClientAuth(true)`?** Want đề nghị cert nhưng có thể cho phép thiếu; need bắt buộc.

**12. SSLContext.getInstance("TLS") có buộc giao thức TLS1.3 không?** Không. TLS version được negotiated theo provider, enabled protocols và peer capabilities.

**13. Có nên disable hostname verification khi gặp PKIX error?** Không. Trust chain và endpoint name là hai kiểm tra độc lập; sửa certificate/truststore/SAN đúng nguyên nhân.

**14. `TrustManagerFactory.init((KeyStore)null)` có nghĩa trust all?** Không; nó dùng default trust material của JSSE/provider/config.

**15. Khi certificate mới được cấp nhưng server vẫn trình cert cũ?** Cần kiểm tra alias selection, SSLContext reload, SNI và connection lifecycle, không chỉ thay file.

**16. Certificate client hợp lệ có bảo đảm quyền nghiệp vụ?** Không. TLS authenticates identity; app vẫn phải authorize action/resource/tenant.

**17. Có nên log SSL debug trong production?** Chỉ khi được phê duyệt, giới hạn thời gian/phạm vi và kiểm soát dữ liệu certificate/session; không log secrets.

**18. Có thể dùng Java 17 cho code này không?** Có. Dùng JSSE, PKCS12, records và APIs Java 17 đã ổn định; mã đã được biên dịch với `--release 17` và chạy xác minh mTLS thật.

## 14. Checklist vận hành

- [ ] Xác định rõ server-auth TLS hay mTLS; bên nào trình identity, bên nào verify peer.
- [ ] KeyManager có đúng PrivateKeyEntry/certificate chain và matching private key.
- [ ] TrustManager có đúng CA/trust anchors cho peer, không import certificates không xác minh.
- [ ] Client kiểm tra SAN/hostname/IP, không tắt endpoint identification.
- [ ] Server mTLS đặt `needClientAuth` nếu bắt buộc client certificate.
- [ ] Đối chiếu EKU, Key Usage, Basic Constraints, chain và thời hạn cert.
- [ ] Không dùng trust-all X509TrustManager hoặc HostnameVerifier trả true.
- [ ] Không bật lại TLS 1.0/1.1, cipher/key algorithms yếu, hoặc hạ JDK security properties một cách tùy tiện.
- [ ] Không hard-code/commit production private keys và passwords; dùng secret manager/HSM khi cần.
- [ ] Có rotation, revocation policy, expiry monitoring và SSLContext reload.
- [ ] Kiểm tra default truststore và Java provider/container image thực tế.
- [ ] Với nhiều tenants/servers, dùng đúng SSLContext/trust scope và SNI/alias selection.
- [ ] Map verified certificate principal sang quyền nghiệp vụ, không mặc định mTLS = full access.
- [ ] Kiểm thử positive và negative: wrong trust, wrong SAN, missing client cert, expired cert.
- [ ] Không in private keys/passwords hoặc detailed production cert identities vào public logs.
- [ ] Duy trì JSSE Java 17+ hiện còn được hỗ trợ, không áp dụng hướng dẫn legacy.

## 15. Nguồn chính thức

- [Java 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): cấu hình KeyManager, TrustManager, SecureRandom.
- [Java 17 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html) và [TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html).
- [Java 17 — X509KeyManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509KeyManager.html) và [X509ExtendedKeyManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedKeyManager.html): identity selection.
- [Java 17 — X509TrustManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509TrustManager.html) và [X509ExtendedTrustManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): peer verification.
- [Java 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): hostname verification, SNI, client auth.
- [Java 25 — SSLParameters](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html): xác nhận API còn được hỗ trợ.
- [Java 17 — SSLServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html) và [SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): TLS sockets/handshake.
- [Java 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): PKCS12 và key/cert entries.
- [Java 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTPS client dùng SSLContext.
- [Oracle Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html).
- [Oracle Java 25 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html).
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html).
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525.html): quy tắc định danh dịch vụ/hostname hiện hành.
