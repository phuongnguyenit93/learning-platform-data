# Cấu hình TLS trong Java: Protocol, cipher suite và yêu cầu xác thực phía khách

## Mục tiêu bài học

Cấu hình TLS không đơn giản là gọi một API bật `https://`. Khi thiết lập một kết nối, hai đầu cần thống nhất **phiên bản giao thức TLS**, **cipher suite** và **quy trình xác thực bằng chứng chỉ**. Trong Java 17+ và JDK hiện hành, lớp **`javax.net.ssl.SSLParameters`** là nơi biểu diễn các lựa chọn này; `SSLContext` cung cấp key/trust managers, còn `SSLSocket`, `SSLServerSocket`, `SSLEngine`, Java `HttpClient` hoặc `HttpsConfigurator` ứng dụng cấu hình vào kết nối cụ thể.

Bài này đặt ba câu hỏi thực tế:

1. **Protocol nào được phép?** `TLSv1.3`, `TLSv1.2` hay một danh sách tương thích? Cần hiểu `supported`, `enabled` và `disabled by security policy` không phải cùng một tập.
2. **Cipher suites nào được phép?** `TLS_AES_128_GCM_SHA256` là TLS 1.3 suite; `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` là ví dụ TLS 1.2 suite. Tên suite phải tương thích phiên bản TLS và điều kiện chứng chỉ/khóa.
3. **Client phải có chứng chỉ không?** `setWantClientAuth(true)` yêu cầu tùy chọn; `setNeedClientAuth(true)` yêu cầu bắt buộc. Server cần **TrustManager** để tin/kiểm chứng client certificate, client cần **KeyManager** để trình certificate nếu mTLS.

Kết thúc bài, bạn có thể:

- Tạo `SSLContext.getInstance("TLS")` và phân biệt `getDefaultSSLParameters()` với `getSupportedSSLParameters()`.
- Thiết lập `SSLParameters.setProtocols(...)`, `setCipherSuites(...)`, `setWantClientAuth(...)`, `setNeedClientAuth(...)` đúng ngữ nghĩa.
- Áp `SSLParameters` cho `SSLServerSocket`/`SSLSocket` và qua `HttpsParameters.setSSLParameters(...)` trong `HttpsConfigurator`.
- Đọc `SSLSession.getProtocol()` và `getCipherSuite()` để biết **đã thương lượng thực tế** gì, thay vì suy ra từ request cấu hình.
- Giải thích vì sao **supported ≠ enabled ≠ negotiated**, và vì sao `jdk.tls.disabledAlgorithms` có quyền chặn cấu hình ứng dụng.
- Hiểu TLS 1.3 cipher suite name không chứa phần key-exchange/authentication giống một số TLS 1.2 suites.
- Phân biệt mTLS identity với authorization của ứng dụng; không dùng client certificate DN như một role mặc định.
- Tạo hai PKCS12 certificates thử bằng `keytool` với SAN IP/DNS, không chứa key production.
- Chạy Java 17+ thực tế với TLS sockets loopback: TLS 1.3 thành công, TLS 1.2 thành công, WANT thiếu cert vẫn thành công, NEED thiếu cert thất bại, NEED có cert được tin thành công; protocol/suite mismatch và hostname mismatch bị từ chối.
- Kiểm thử **38 phép assertion thực**, đã biên dịch bằng `javac --release 17` và chạy trên OpenJDK 24.

**Special Note:** Chỉ dùng kiến thức Java/TLS **còn hiệu lực hiện nay**. Ưu tiên TLS 1.3/TLS 1.2, cipher suites có xác thực và mã hóa an toàn, `SSLParameters`, `KeyManagerFactory`, `TrustManagerFactory` và chuẩn PKCS12. Không bật SSLv3/TLS 1.0/1.1, RC4, 3DES, cipher vô danh/NULL, không hạ `jdk.tls.disabledAlgorithms` để “sửa” handshake, không dùng trust-all hay tắt kiểm tra hostname. Các setters trực tiếp `HttpsParameters.setProtocols`, `setCipherSuites`, `setNeedClientAuth` và `setWantClientAuth` đã **deprecated từ JDK 23**, nên khi cấu hình HTTPS server cần đi qua `SSLParameters`.

## 1. Ba trục cấu hình TLS độc lập nhưng cùng quyết định handshake

```text
SERVER SSLParameters                      CLIENT SSLParameters
  enabled protocols                        enabled protocols
  enabled cipher suites                    enabled cipher suites
  NONE / WANT / NEED client auth            client identity (nếu có)
      |                                          |
      +--------------------+---------------------+
                           |
                           v
                   TLS negotiation
                           |
              +------------+-------------+
              |                          |
         Có giao nhau                Không giao nhau /
         + cert/trust OK              cert/trust sai
              |                          |
              v                          v
         SSLSession                    TLS handshake
         protocol+cipher               thất bại
         verified principals            (chưa có HTTP response)
```

TLS thành công khi tất cả điều kiện tương thích được đáp ứng, không chỉ vì hai bên gọi `SSLContext.getInstance("TLS")`. Việc kiểm tra Certificate chain và endpoint identity là **bắt buộc** khi peer được xác thực. mTLS còn yêu cầu server xác minh client cert nếu `needClientAuth` bật.

Một TLS handshake có thể thất bại do:

- Không có TLS protocol version nào **được cả hai đầu cho phép và security policy cho phép**.
- Không có cipher suite chung tương thích protocol/keys.
- Cipher suite dùng thuật toán/độ dài khóa bị security policy disable.
- Server không có private key hoặc chứng chỉ phù hợp.
- Client không trust server certificate chain hoặc hostname/IP SAN không khớp.
- Server yêu cầu chứng chỉ client nhưng client không gửi hoặc server không tin certificate chain.
- Provider, disabled algorithms, signature algorithms, groups, certificate EKU và policy không tương thích.

**Không trả HTTP 401/403 khi TLS handshake fail**, bởi chưa có request HTTP thành công để handler trả mã trạng thái.

## 2. `SSLContext` và `SSLParameters` không phải cùng một đối tượng

`SSLContext` là nền tảng JSSE tạo TLS sockets/engines với key/trust managers:

```java
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, new SecureRandom());
```

Đây là **snippet** có `keyManagers`/`trustManagers` được thiết lập theo vai trò client/server. `SSLContext.getInstance("TLS")` chưa đồng nghĩa đã nạp private key của HTTPS server; server `SSLContext.init(...)` phải nhận key material từ `KeyManagerFactory`. Khi mTLS, server còn cần TrustManagers để xác minh client certificate.

`SSLParameters` mô tả **cách một kết nối cụ thể được cấu hình**:

```java
SSLParameters params = context.getDefaultSSLParameters();
params.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
params.setNeedClientAuth(true); // Chỉ có ý nghĩa ở server mode.
```

Đây là snippet minh họa chính sách mTLS, không phải chương trình tự chạy. Gọi setters trên một object `SSLParameters` **không tự thay đổi mọi socket đã tạo**: phải áp bằng `setSSLParameters` trên đúng socket/engine hoặc `HttpsParameters.setSSLParameters` trong configurator trước khi handshake.

### 2.1. Ba cấp độ `supported`, `enabled`, `negotiated`

| Cấp | Java API | Ý nghĩa |
| --- | --- | --- |
| **Supported** | `context.getSupportedSSLParameters()` | Provider biết cách hỗ trợ những protocols/suites nào; chưa chắc được phép dùng |
| **Default-enabled** | `context.getDefaultSSLParameters()` | Tập mặc định phù hợp context/provider; có thể thay đổi theo phiên bản/security policy |
| **Explicit-enabled** | `socket.setSSLParameters(params)` | App chỉ định những lựa chọn thử thương lượng cho kết nối |
| **Disabled** | `Security.getProperty("jdk.tls.disabledAlgorithms")` | Security policy có thể chặn protocol/suite dù provider có nhận tên đó |
| **Negotiated** | `socket.getSession().getProtocol()/getCipherSuite()` | Kết quả thực của một handshake thành công |

Không kết luận “suite X an toàn và đang được dùng” chỉ vì nó có trong `getSupportedSSLParameters().getCipherSuites()`. `supported` có thể gồm các thuật toán cũ/không bật; `disabledAlgorithms` có thể chặn chúng ngay trong handshake.

### 2.2. Kiểm tra tại runtime thay vì hardcode giả định

```java
SSLParameters supported = context.getSupportedSSLParameters();
SSLParameters defaults = context.getDefaultSSLParameters();

System.out.println(Arrays.toString(supported.getProtocols()));
System.out.println(Arrays.toString(defaults.getProtocols()));
System.out.println(Arrays.toString(defaults.getCipherSuites()));
System.out.println(Security.getProperty("jdk.tls.disabledAlgorithms"));
```

Đây là **snippet để khảo sát**, output thay đổi theo JDK/provider/security properties; không đưa một danh sách “đúng cho mọi runtime”. Nếu cần đảm bảo một profile có mặt, assert tên protocol/suite trong `getSupported...` và **chạy handshake thật** trên nền tảng mục tiêu.

## 3. Protocol versions: TLS 1.3 và TLS 1.2

`SSLParameters.setProtocols(String[])` quy định các phiên bản được bật trên một endpoint:

```java
SSLParameters params = context.getDefaultSSLParameters();
params.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
serverSocket.setSSLParameters(params);
```

Đây là snippet cần `SSLContext context` và `SSLServerSocket serverSocket` đã được tạo. TLS 1.3 là lựa chọn hiện đại; TLS 1.2 vẫn được hỗ trợ rộng rãi với cấu hình cipher tốt. Nếu toàn bộ client đều hỗ trợ TLS 1.3, có thể dùng profile chỉ `TLSv1.3` sau khi kiểm thử interoperability.

### 3.1. Giao nhau về protocols là điều kiện cần

| Server bật | Client bật | Kết quả kỳ vọng |
| --- | --- | --- |
| Chỉ `TLSv1.3` | Chỉ `TLSv1.3` | Có protocol chung; còn phải thỏa điều kiện cipher/cert |
| Chỉ `TLSv1.2` | Chỉ `TLSv1.2` | Có protocol chung |
| `TLSv1.3` và `TLSv1.2` | Chỉ `TLSv1.2` | Có thể dùng TLS 1.2 |
| Chỉ `TLSv1.3` | Chỉ `TLSv1.2` | **Handshake thất bại** |
| Chỉ phiên bản cũ đã bị disable | Phiên bản tương ứng | **Không khôi phục được bằng app setter** |

Tài liệu Oracle JDK 26 liệt kê nhiều protocol names hỗ trợ ở tầng provider, nhưng `jdk.tls.disabledAlgorithms` chặn các bản lỗi thời như TLS 1.0/1.1 trong cấu hình hiện đại. **Không** gỡ lệnh cấm trong `java.security` hoặc hạ mức bảo mật chỉ để tương thích với client cũ; nâng cấp client.

### 3.2. Negotiation không nhất thiết chọn phiên bản theo thứ tự mảng

Danh sách protocols được bật là **tập lựa chọn**, không bảo đảm một thuật toán “đầu tiên trong mảng” sẽ được chọn trong mọi JSSE provider. TLS handshake/protocol logic và policy của hai đầu quyết định. Hãy đọc `SSLSession.getProtocol()` sau khi handshake thành công thay vì log lại giá trị đã yêu cầu.

### 3.3. TLS 1.3 có thay đổi thực chất

TLS 1.3 thay đổi key exchange, handshake và cipher-suite naming so với TLS 1.2. Không giả định suites có hậu tố kiểu `ECDHE_RSA` bắt buộc thuộc TLS 1.3; việc xác thực server bằng certificate và signature algorithms được thương lượng theo các cơ chế riêng.

## 4. Cipher suite: tên có ý nghĩa khác theo TLS version

**Cipher suite** chỉ định tổ hợp cryptographic algorithms dùng cho một TLS session. Không phải “một mật mã AES đơn lẻ”. Ví dụ JDK SunJSSE hỗ trợ các suites sau trong fixture:

| Protocol | Ví dụ cipher suite | Ý nghĩa khái quát |
| --- | --- | --- |
| TLS 1.3 | `TLS_AES_128_GCM_SHA256` | AEAD AES-128-GCM + HKDF hash SHA-256; authentication/key exchange được chọn riêng |
| TLS 1.2 | `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | Ephemeral ECDHE key exchange, RSA certificate authentication, AES-128-GCM, SHA-256 |
| TLS 1.2 | `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384` | ECDHE/RSA + AES-256-GCM, SHA-384 |

Các tên này có trong **OpenJDK 24 SunJSSE** mà bài đã dùng để kiểm thử. Một JDK/FIPS provider khác có thể không cho sử dụng một số suites; thực hiện provider-policy checks trước khi quyết định allowlist.

### 4.1. TLS 1.3 không mã hóa RSA/ECDHE trong tên suite

`TLS_AES_128_GCM_SHA256` **không** nói rằng key exchange là RSA hoặc rằng certificate có một thuật toán cố định. TLS 1.3 thương lượng key share và signature algorithms thông qua các extension/handshake khác. Vì vậy không đọc nó như một TLS 1.2-style `TLS_ECDHE_RSA_WITH_...`.

### 4.2. AES-GCM là authenticated encryption

AES-GCM là **AEAD** (Authenticated Encryption with Associated Data). Trong việc thiết kế profile hiện đại, AES-GCM hoặc các AEAD suites phù hợp provider thường được ưu tiên hơn bộ mật mã cũ có vấn đề; nhưng **không hardcode tất cả suites vào mọi service**. TLS 1.3 còn hỗ trợ các suite khác tùy provider, ví dụ ChaCha20-Poly1305. Cần cân nhắc client compatibility, compliance, hardware, security patches.

### 4.3. `setCipherSuites` chỉ giới hạn suites được thử, không bỏ security policy

```java
SSLParameters server = context.getDefaultSSLParameters();
server.setProtocols(new String[] {"TLSv1.2"});
server.setCipherSuites(new String[] {
    "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"
});
socket.setSSLParameters(server);
```

Đây là snippet, cần `socket` hỗ trợ `setSSLParameters`. Nó **không** thay đổi toàn JVM security property. Nếu `jdk.tls.disabledAlgorithms` cấm một thành phần crypto, việc app gửi một tên suite qua `setCipherSuites` không làm nó được phép handshake.

### 4.4. Mismatch do cipher, ngay cả khi protocol chung

Ví dụ phía server chỉ bật `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`, phía client chỉ bật `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384`, cả hai chỉ bật `TLSv1.2`. Hai suites đều có thể supported nhưng **không có suite chung**, handshake phải fail. Fixture kiểm thử thực tế case này.

### 4.5. Không hứa cipher suites mặc định là danh sách bất biến

Tập default-enabled suites có thể thay đổi theo JDK update, provider/FIPS mode, certificate algorithm và security properties. **Kiểm chứng ở runtime** và kiểm thử thực tế trước khi deploy. Nếu dịch vụ chưa có yêu cầu compliance đặc thù, giữ JSSE defaults an toàn và thiết lập phiên bản TLS là lựa chọn hợp lý hơn sao chép một allowlist cũ thiếu TLS 1.3.

## 5. Phân biệt ba chế độ xác thực client

`SSLParameters` có hai setters quan trọng cho **server mode**:

```java
ssl.setNeedClientAuth(true); // bắt buộc xác minh client certificate
ssl.setWantClientAuth(true); // chỉ yêu cầu tùy chọn
```

Đây là **hai dòng minh họa các chính sách thay thế**, **không được gọi liên tiếp** rồi mong cả hai đều true: setter sau có thể reset setter trước. Trong code thực, chọn **một** trạng thái:

| Chế độ | Cấu hình trên server SSLParameters | Client thiếu certificate | Server có peer principal? |
| --- | --- | --- | --- |
| NONE | `setNeedClientAuth(false)` | Có thể handshake thành công nếu server cert/trust đúng | Không |
| WANT | `setWantClientAuth(true)` | **Vẫn có thể handshake thành công** | Có nếu client thực sự trình cert được tin |
| NEED | `setNeedClientAuth(true)` | **Handshake phải thất bại** | Có khi client được xác minh thành công |

### 5.1. WANT không phải mTLS bắt buộc

`wantClientAuth` hữu ích cho giao thức cho phép client-certificate identity **tùy chọn**, nhưng app phải xử lý rõ trường hợp `getPeerPrincipal()` vắng mặt. Không dùng WANT nếu yêu cầu nghiệp vụ là “mọi client phải có chứng chỉ”.

**Một client có certificate nhưng certificate không được tin** vẫn có thể gặp TLS handshake lỗi tùy quá trình certificate verification, ngay cả ở WANT; chữ “optional” không có nghĩa “tin mọi certificate gửi đến”.

### 5.2. NEED thật sự đòi cả hai phía có cấu hình đúng

Để NEED thành công:
- Server `SSLContext` phải có KeyManagers trình **server identity**.
- Server cần TrustManagers **tin client CA/certificate**.
- Client cần TrustManagers tin **server CA/certificate** và kiểm tra SAN/hostname.
- Client cần KeyManagers trình **client private key + certificate**.
- `SSLParameters.setNeedClientAuth(true)` phải được **áp trước handshake**.

Nếu client chỉ có truststore tin server nhưng **không có client identity**, mTLS NEED sẽ fail (đã kiểm thử).

### 5.3. Setter WANT/NEED ghi đè lẫn nhau

Javadoc `SSLParameters` và `SSLServerSocket` mô tả hai client-auth flags là trạng thái loại trừ nhau. Fixture có ba kiểm tra:

```java
SSLParameters auth = context.getDefaultSSLParameters();
auth.setNeedClientAuth(true);
assert auth.getNeedClientAuth() && !auth.getWantClientAuth();

auth.setWantClientAuth(true);
assert auth.getWantClientAuth() && !auth.getNeedClientAuth();
```

Đây là snippet độc lập trong cùng context `context`, không phải code của một `main` hoàn chỉnh. **Đừng gọi want sau need** trong production config rồi nghĩ server còn yêu cầu client cert bắt buộc.

## 6. `SSLContext`: identity material và trust material

### 6.1. Keystore của server

Dùng `KeyStore.getInstance("PKCS12")` và `KeyManagerFactory` để nạp certificate/private-key entry:

```java
KeyStore store = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(serverPath)) {
    store.load(in, password);
}
KeyManagerFactory keys = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keys.init(store, password);

SSLContext serverContext = SSLContext.getInstance("TLS");
serverContext.init(keys.getKeyManagers(), trustManagers, new SecureRandom());
```

Đây là snippet; `serverPath`, `password`, `trustManagers` phải do ứng dụng cung cấp. Với server xác thực client, `trustManagers` lấy từ `TrustManagerFactory` chứa **chứng chỉ/CA client được tin**. Với HTTPS một chiều, không bật NEED, server có thể dùng default trust managers nếu không yêu cầu peer cert.

### 6.2. Client truststore không chứa server private key

`TrustManagerFactory` nhận một truststore chứa trusted certificate hoặc CA anchors. Với fixture self-signed, client tin đúng cert thử nghiệm, không trust-all. Trong production, trust anchors cần được phát hành/quản lý qua PKI, không phải mỗi client được copy private key server.

### 6.3. Client keystore khi mTLS

Client mTLS có keystore `client.p12` gồm private key và client cert, được nạp vào `KeyManagerFactory`; client `SSLContext.init(clientKeyManagers, serverTrustManagers, ...)`. Server xác minh chain của client cert qua trust manager server.

### 6.4. Không đồng nhất certificate identity và role

Một client cert có subject DN chứa `CN=demo-client` chỉ là **verified peer identity** theo TLS trust policy. App phải map nó vào service account/user principal rồi kiểm tra **authorization** trên method/resource. TLS và RBAC/ABAC là hai lớp khác nhau.

## 7. Áp SSLParameters cho đúng đối tượng trước handshake

### 7.1. SSLServerSocket

```java
SSLServerSocket listener = (SSLServerSocket)
        serverContext.getServerSocketFactory()
            .createServerSocket(0, 5, InetAddress.getByName("127.0.0.1"));

SSLParameters p = listener.getSSLParameters();
p.setProtocols(new String[]{"TLSv1.3", "TLSv1.2"});
p.setNeedClientAuth(true);
listener.setSSLParameters(p);
```

Đây là snippet, cần `serverContext` có **server KeyManagers và TrustManagers tin client cert**; nếu không, NEED có thể làm handshake fail. `SSLServerSocket` dùng cấu hình cho **các sockets được accept sau đó**. Không nghĩ `listener.setSSLParameters(p)` tự sửa mọi connection đã accept trước.

### 7.2. SSLSocket ở phía client

```java
SSLParameters client = socket.getSSLParameters();
client.setProtocols(new String[]{"TLSv1.3", "TLSv1.2"});
client.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(client);
socket.startHandshake();
```

Đây là snippet cần `SSLSocket socket`. Khi dùng **low-level SSLSocket**, hãy bật **HTTPS endpoint identification** theo hostname/IP đích nếu socket được dùng cho HTTPS-like validation. Không đồng nhất việc trust certificate với kiểm tra tên đích; chúng là hai điều kiện riêng.

**Java `HttpClient` HTTPS mặc định có endpoint hostname verification**; snippet này đặc biệt có ý nghĩa khi bạn trực tiếp dùng `SSLSocket`/`SSLEngine` thay cho một HTTP client được quản lý.

### 7.3. HttpsServer + HttpsConfigurator

Nếu dùng `com.sun.net.httpserver.HttpsServer`:

```java
server.setHttpsConfigurator(new HttpsConfigurator(sslContext) {
    @Override
    public void configure(HttpsParameters params) {
        SSLParameters policy = getSSLContext().getDefaultSSLParameters();
        policy.setProtocols(new String[]{"TLSv1.3", "TLSv1.2"});
        policy.setNeedClientAuth(true);
        params.setSSLParameters(policy);
    }
});
```

Đây là snippet có `HttpsServer server`, `SSLContext sslContext` đã init; `SSLContext` phải có server KeyManager và server TrustManager để xác minh client cert. **Không** dùng `params.setProtocols(...)` hoặc `params.setNeedClientAuth(...)` trong code mới vì setters trực tiếp trên `HttpsParameters` đã deprecated từ JDK 23.

`HttpsConfigurator.configure` là TLS **connection-level** callback, không đảm bảo được gọi lại cho từng HTTP request khi connection reuse. Cấu hình protocol/cipher/clientAuth thuộc handshake, không phải thông số thay đổi giữa các requests trên cùng kết nối.

### 7.4. SSLEngine và ứng dụng nonblocking

`SSLEngine` cũng hỗ trợ `setSSLParameters` và `setUseClientMode`; nó là API TLS state machine cho nonblocking transports. Bài này sử dụng `SSLSocket` để nhìn rõ handshake với ít ceremony; **không** tự tạo một `SSLEngine` half-implemented để xử lý nonblocking TLS trong production.

## 8. Security properties: chặn cipher/protocol ở cấp JDK

`jdk.tls.disabledAlgorithms` là **Java security property** của JSSE (Oracle/OpenJDK implementation), có thể giới hạn protocols, cipher suites, khóa và thuật toán chữ ký. `jdk.certpath.disabledAlgorithms` có thể hạn chế thuật toán/độ dài khóa khi xác minh certificate chain. Cấu hình cụ thể ở `<java-home>/conf/security/java.security` và có thể được hạ tầng quản lý theo chính sách.

```java
String disabled = Security.getProperty("jdk.tls.disabledAlgorithms");
System.out.println(disabled);
```

Đây là **snippet**, giá trị thay đổi theo JDK/distribution/runtime. Không nên đưa một chuỗi property cứng rồi bảo mọi JDK đều giống.

### Disabled khác not-enabled

- **Supported:** provider có implementation.
- **Not-enabled:** app/provider chưa đưa vào tập suites được thử mặc định; có thể bật khi policy cho phép.
- **Disabled:** bị security property chặn; cho tên qua `setCipherSuites` hoặc `setProtocols` **không làm handshake dùng được thuật toán đó**.

Không vô hiệu hóa security properties để làm một client SSL 3.0/TLS 1.0 hay RC4 test pass. Đó là hướng ngược với Special Note.

### JDK 26 providers

Tài liệu SunJSSE vẫn liệt kê tên `TLSv1`/`TLSv1.1` ở danh sách provider protocols, nhưng chúng **bị disabled by default bởi security constraints**. Đọc bảng “supported” mà kết luận “nên bật” là sai. Chọn TLS 1.2/1.3 và cập nhật môi trường thật.

### System properties và thứ tự ưu tiên

Java có provider-specific properties như `jdk.tls.client.protocols`, `jdk.tls.server.cipherSuites` và các security properties. Ứng dụng explicit `SSLParameters` có thể tác động enabled choices; security constraints vẫn cần được tôn trọng. Thứ tự áp dụng và ý nghĩa các options tùy provider/JDK, nên quản trị cấu hình ở một nơi rõ ràng, kiểm thử runtime thay vì “đoán” ưu tiên từ tên property.

### Không hardcode tất cả cipher suites trong mọi hệ thống

Trong fixture kiểm thử, cố ý đặt **mỗi scenario chỉ một cipher suite** để chứng minh chính xác handshake pass/fail. Production **không** mặc định nên khóa đúng một cipher: cần provider/interoperability policy đã được kiểm chứng và khả năng cập nhật TLS security theo JDK patches.

## 9. Bảng hành vi TLS cần kiểm thử

| Kịch bản | Server | Client | Kỳ vọng |
| --- | --- | --- | --- |
| TLS 1.3 thành công | Chỉ TLSv1.3, AES_128_GCM_SHA256 | Cùng protocol/suite, trust server | Thành công |
| TLS 1.2 thành công | Chỉ TLSv1.2, ECDHE_RSA AES_128_GCM_SHA256 | Cùng protocol/suite | Thành công |
| WANT thiếu cert | `wantClientAuth=true` | Có trust server, **không có client cert** | Thành công, không có peer principal |
| NEED thiếu cert | `needClientAuth=true` | Không có client cert | Thất bại |
| NEED có cert | Server tin client cert | Client có keypair/cert và tin server | Thành công, có peer principal |
| Protocol không giao nhau | Chỉ TLSv1.3 | Chỉ TLSv1.2 | Thất bại |
| Cipher suite không giao nhau | TLSv1.2/C12A | TLSv1.2/C12B | Thất bại |
| Hostname không khớp SAN | Cert SAN 127.0.0.1/localhost | Yêu cầu hostname `wrong.example`, endpoint check bật | Thất bại |
| NEED/WANT setters nối tiếp | setNeed rồi setWant | Không liên quan | Setter sau thay chính sách |
| TLS version được disabled | Có tên ở supported nhưng bị policy chặn | Cố bật qua app | Không được bỏ qua policy |

**Cảnh báo:** Handshake thất bại không có một exception message duy nhất cho mọi provider; tests nên assert **không có TLS session thành công**, không hardcode thông điệp tiếng Anh của một JDK release.

## 10. Chứng chỉ thử nghiệm an toàn bằng keytool

Test dùng hai keystores **tạo tạm trên loopback**, không có production secrets:

- `server.p12`: RSA 2048, SHA256withRSA, CN=localhost, `SAN=ip:127.0.0.1,dns:localhost`, `EKU=serverAuth`, validity 2 ngày.
- `client.p12`: RSA 2048, SHA256withRSA, CN=demo-client, `EKU=clientAuth`, validity 2 ngày.

Đây là chứng chỉ **self-signed thử nghiệm**, client chỉ trust certificate được pin rõ ràng trong in-memory truststore. **Không** dùng trust-all hoặc bỏ hostname verification.

### Windows PowerShell

Tạo một thư mục **test mới**, đặt file Java phía dưới ở đó:

```powershell
$env:TLS_DEMO_PASSWORD = "demo-only-324-not-for-production"

keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 2 -storetype PKCS12 -keystore server.p12 -storepass $env:TLS_DEMO_PASSWORD -keypass $env:TLS_DEMO_PASSWORD -dname "CN=localhost, OU=Test, O=Demo, L=HCMC, ST=HCMC, C=VN" -ext "SAN=ip:127.0.0.1,dns:localhost" -ext "EKU=serverAuth" -noprompt

keytool -genkeypair -alias client -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 2 -storetype PKCS12 -keystore client.p12 -storepass $env:TLS_DEMO_PASSWORD -keypass $env:TLS_DEMO_PASSWORD -dname "CN=demo-client, OU=Test, O=Demo, L=HCMC, ST=HCMC, C=VN" -ext "EKU=clientAuth" -noprompt

javac --release 17 TlsPolicyMatrixDemo.java
java TlsPolicyMatrixDemo server.p12 client.p12
```

### POSIX shell (Linux/macOS)

```bash
export TLS_DEMO_PASSWORD='demo-only-324-not-for-production'

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

javac --release 17 TlsPolicyMatrixDemo.java
java TlsPolicyMatrixDemo server.p12 client.p12
```

**Bảo mật:** `keytool -storepass` trong command line và env variable demo không an toàn cho credentials production; dùng secret-management mechanisms/permissions và chính sách quản trị key thật. Chỉ chạy `keytool -genkeypair` trong một thư mục tạm không chứa files dịch vụ. Xóa keystores test sau kiểm tra; không commit hoặc tải chúng lên.

## 11. Ví dụ Java 17+ đầy đủ: TLS protocol/cipher/client-auth matrix

### 11.1. Mục đích và những gì đã chạy

Một file **`TlsPolicyMatrixDemo.java`** khởi chạy các **SSLSocket ↔ SSLServerSocket TLS connections thực** qua `127.0.0.1`. Server và client được cấu hình `SSLParameters` trước handshake. Server thread đọc byte `65` từ client rồi trả byte `66` **chỉ sau khi TLS thành công**, tránh nhầm trường hợp handshake có vẻ xong một phía nhưng peer thực sự từ chối.

Fixture có timeouts, executor cleanup, close sockets/streams, không tạo remote connection; client dùng `setEndpointIdentificationAlgorithm("HTTPS")`. 38 checks đều phải PASS mới chương trình thoát bình thường. Hai file `PKCS12` phải tạo trước theo mục 10.

Kết quả đã được thực thi trên Windows **OpenJDK 24**, biên dịch nguồn qua `javac --release 17`. Các suite names `TLS_AES_128_GCM_SHA256`, `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` và `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384` được SunJSSE của môi trường test hỗ trợ. Trên provider/FIPS khác, bài test có thể cần dùng suite names thuộc security profile thực tế — **không mở suite yếu chỉ để pass**.

### 11.2. Toàn bộ file `TlsPolicyMatrixDemo.java`

```java
import java.io.InputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.Security;
import java.security.cert.Certificate;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLPeerUnverifiedException;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLServerSocketFactory;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManagerFactory;

public final class TlsPolicyMatrixDemo {
    private static final String TLS13 = "TLSv1.3";
    private static final String TLS12 = "TLSv1.2";
    private static final String C13 = "TLS_AES_128_GCM_SHA256";
    private static final String C12A = "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256";
    private static final String C12B = "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384";

    private enum ClientAuth { NONE, WANT, NEED }
    private record ServerResult(boolean success, String protocol,
                                String cipher, String peerPrincipal) {}
    private record Attempt(boolean success, String protocol, String cipher,
                           String peerPrincipal, boolean need, boolean want,
                           boolean endpointIdentification) {}

    private static KeyStore load(Path path, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(path)) {
            store.load(input, password);
        }
        return store;
    }

    private static TrustManagerFactory trust(Certificate certificate)
            throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        store.load(null, null);
        store.setCertificateEntry("trusted", certificate);
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(store);
        return factory;
    }

    private static SSLContext serverContext(KeyStore serverKeys,
                                             char[] password,
                                             Certificate clientCertificate)
            throws Exception {
        KeyManagerFactory keys = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keys.init(serverKeys, password);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keys.getKeyManagers(),
                clientCertificate == null ? null
                        : trust(clientCertificate).getTrustManagers(),
                new SecureRandom());
        return context;
    }

    private static SSLContext clientContext(Certificate serverCertificate,
                                             KeyStore clientKeys,
                                             char[] password)
            throws Exception {
        KeyManagerFactory keys = null;
        if (clientKeys != null) {
            keys = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            keys.init(clientKeys, password);
        }
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keys == null ? null : keys.getKeyManagers(),
                trust(serverCertificate).getTrustManagers(), new SecureRandom());
        return context;
    }

    private static Attempt attempt(SSLContext serverCtx, SSLContext clientCtx,
                                   String[] serverProtocols,
                                   String[] clientProtocols,
                                   String[] serverSuites,
                                   String[] clientSuites,
                                   ClientAuth auth, boolean wrongHostname)
            throws Exception {
        SSLServerSocketFactory listenerFactory = serverCtx.getServerSocketFactory();
        ExecutorService service = Executors.newSingleThreadExecutor();
        try (SSLServerSocket listener = (SSLServerSocket)
                listenerFactory.createServerSocket(0, 5,
                        InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(4000);
            SSLParameters serverParams = listener.getSSLParameters();
            serverParams.setProtocols(serverProtocols);
            serverParams.setCipherSuites(serverSuites);
            if (auth == ClientAuth.NEED) {
                serverParams.setNeedClientAuth(true);
            } else if (auth == ClientAuth.WANT) {
                serverParams.setWantClientAuth(true);
            } else {
                serverParams.setNeedClientAuth(false);
            }
            listener.setSSLParameters(serverParams);
            boolean need = listener.getNeedClientAuth();
            boolean want = listener.getWantClientAuth();

            Future<ServerResult> pending = service.submit(() -> {
                try (SSLSocket serverSide = (SSLSocket) listener.accept()) {
                    serverSide.setSoTimeout(4000);
                    serverSide.startHandshake();
                    String protocol = serverSide.getSession().getProtocol();
                    String cipher = serverSide.getSession().getCipherSuite();
                    String principal;
                    try {
                        principal = serverSide.getSession()
                                .getPeerPrincipal().getName();
                    } catch (SSLPeerUnverifiedException noClientCert) {
                        principal = "none";
                    }
                    int requestByte = serverSide.getInputStream().read();
                    if (requestByte != 65) {
                        throw new IOException("bad test data");
                    }
                    serverSide.getOutputStream().write(66);
                    serverSide.getOutputStream().flush();
                    return new ServerResult(true, protocol, cipher, principal);
                } catch (IOException ex) {
                    return new ServerResult(false, "", "", "");
                }
            });

            SSLSocketFactory factory = clientCtx.getSocketFactory();
            boolean clientOk = false;
            boolean verifyHost = false;
            String clientProtocol = "";
            String clientCipher = "";
            try {
                SSLSocket client;
                int port = listener.getLocalPort();
                if (wrongHostname) {
                    Socket transport = new Socket("127.0.0.1", port);
                    client = (SSLSocket) factory.createSocket(
                            transport, "wrong.example", port, true);
                } else {
                    client = (SSLSocket) factory.createSocket("127.0.0.1", port);
                }
                try (client) {
                    client.setSoTimeout(4000);
                    SSLParameters params = client.getSSLParameters();
                    params.setProtocols(clientProtocols);
                    params.setCipherSuites(clientSuites);
                    params.setEndpointIdentificationAlgorithm("HTTPS");
                    client.setSSLParameters(params);
                    verifyHost = "HTTPS".equals(client.getSSLParameters()
                            .getEndpointIdentificationAlgorithm());
                    client.startHandshake();
                    clientProtocol = client.getSession().getProtocol();
                    clientCipher = client.getSession().getCipherSuite();
                    client.getOutputStream().write(65);
                    client.getOutputStream().flush();
                    clientOk = client.getInputStream().read() == 66;
                }
            } catch (IOException expectedHandshakeFailure) {
                // A rejection is a normal result in the negative scenarios.
            }

            ServerResult server = pending.get(7, TimeUnit.SECONDS);
            boolean success = clientOk && server.success();
            String negotiatedProtocol = success ? server.protocol() : clientProtocol;
            String negotiatedCipher = success ? server.cipher() : clientCipher;
            return new Attempt(success, negotiatedProtocol, negotiatedCipher,
                    server.peerPrincipal(), need, want, verifyHost);
        } finally {
            service.shutdownNow();
        }
    }

    private static void check(String name, boolean value) {
        if (!value) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2)
            throw new IllegalArgumentException("server.p12 client.p12 required");
        String secret = System.getenv("TLS_DEMO_PASSWORD");
        if (secret == null || secret.isBlank())
            throw new IllegalStateException("TLS_DEMO_PASSWORD is required");
        char[] password = secret.toCharArray();
        try {
            KeyStore serverKeys = load(Path.of(args[0]), password);
            KeyStore clientKeys = load(Path.of(args[1]), password);
            Certificate serverCert = serverKeys.getCertificate("server");
            Certificate clientCert = clientKeys.getCertificate("client");
            check("serverPrivateKeyPresent", serverKeys.isKeyEntry("server"));
            check("clientPrivateKeyPresent", clientKeys.isKeyEntry("client"));
            check("serverCertificatePresent", serverCert != null);
            check("clientCertificatePresent", clientCert != null);
            SSLContext serverNormal = serverContext(serverKeys, password, null);
            SSLContext serverWithClientTrust = serverContext(
                    serverKeys, password, clientCert);
            SSLContext clientNoIdentity = clientContext(
                    serverCert, null, password);
            SSLContext clientWithIdentity = clientContext(
                    serverCert, clientKeys, password);
            SSLParameters supported = serverNormal.getSupportedSSLParameters();
            SSLParameters defaults = serverNormal.getDefaultSSLParameters();

            check("tls13Supported",
                    Arrays.asList(supported.getProtocols()).contains(TLS13));
            check("tls12Supported",
                    Arrays.asList(supported.getProtocols()).contains(TLS12));
            check("tls13GcmSuiteSupported",
                    Arrays.asList(supported.getCipherSuites()).contains(C13));
            check("tls12Gcm128SuiteSupported",
                    Arrays.asList(supported.getCipherSuites()).contains(C12A));
            check("tls12Gcm256SuiteSupported",
                    Arrays.asList(supported.getCipherSuites()).contains(C12B));
            check("defaultProtocolsNonempty", defaults.getProtocols().length > 0);
            check("defaultCipherSuitesNonempty", defaults.getCipherSuites().length > 0);
            check("disabledAlgorithmsPolicyPresent",
                    Security.getProperty("jdk.tls.disabledAlgorithms") != null);

            SSLParameters authPolicy = serverNormal.getDefaultSSLParameters();
            authPolicy.setNeedClientAuth(true);
            check("needFlagTrue", authPolicy.getNeedClientAuth());
            check("needClearsWant", !authPolicy.getWantClientAuth());
            authPolicy.setWantClientAuth(true);
            check("wantFlagTrue", authPolicy.getWantClientAuth());
            check("wantClearsNeed", !authPolicy.getNeedClientAuth());
            authPolicy.setNeedClientAuth(true);
            check("needCanBeRestored",
                    authPolicy.getNeedClientAuth() && !authPolicy.getWantClientAuth());

            Attempt v13 = attempt(serverNormal, clientNoIdentity,
                    new String[]{TLS13}, new String[]{TLS13},
                    new String[]{C13}, new String[]{C13},
                    ClientAuth.NONE, false);
            check("tls13HandshakeSuccess", v13.success());
            check("tls13Negotiated", TLS13.equals(v13.protocol()));
            check("tls13GcmCipherNegotiated", C13.equals(v13.cipher()));
            check("tls13ClientNotRequired", !v13.need() && !v13.want());
            check("tls13PeerUnauthenticated", "none".equals(v13.peerPrincipal()));
            check("clientEndpointIdentificationOn", v13.endpointIdentification());

            Attempt v12 = attempt(serverNormal, clientNoIdentity,
                    new String[]{TLS12}, new String[]{TLS12},
                    new String[]{C12A}, new String[]{C12A},
                    ClientAuth.NONE, false);
            check("tls12HandshakeSuccess", v12.success());
            check("tls12Negotiated", TLS12.equals(v12.protocol()));
            check("tls12GcmCipherNegotiated", C12A.equals(v12.cipher()));

            Attempt want = attempt(serverWithClientTrust, clientNoIdentity,
                    new String[]{TLS13}, new String[]{TLS13},
                    new String[]{C13}, new String[]{C13},
                    ClientAuth.WANT, false);
            check("wantWithoutCertificateSucceeds", want.success());
            check("wantFlagOnServer", want.want() && !want.need());
            check("wantPeerAbsent", "none".equals(want.peerPrincipal()));

            Attempt needMissing = attempt(serverWithClientTrust, clientNoIdentity,
                    new String[]{TLS13}, new String[]{TLS13},
                    new String[]{C13}, new String[]{C13},
                    ClientAuth.NEED, false);
            check("needWithoutCertificateRejected", !needMissing.success());
            check("needFlagOnServer", needMissing.need() && !needMissing.want());

            Attempt needVerified = attempt(serverWithClientTrust, clientWithIdentity,
                    new String[]{TLS13}, new String[]{TLS13},
                    new String[]{C13}, new String[]{C13},
                    ClientAuth.NEED, false);
            check("needWithCertificateSucceeds", needVerified.success());
            check("needClientPrincipalVerified",
                    needVerified.peerPrincipal().contains("CN=demo-client"));
            check("needProtocolTls13", TLS13.equals(needVerified.protocol()));

            Attempt noSharedProtocol = attempt(serverNormal, clientNoIdentity,
                    new String[]{TLS13}, new String[]{TLS12},
                    new String[]{C13, C12A}, new String[]{C13, C12A},
                    ClientAuth.NONE, false);
            check("noSharedProtocolRejected", !noSharedProtocol.success());

            Attempt noSharedCipher = attempt(serverNormal, clientNoIdentity,
                    new String[]{TLS12}, new String[]{TLS12},
                    new String[]{C12A}, new String[]{C12B},
                    ClientAuth.NONE, false);
            check("noSharedCipherRejected", !noSharedCipher.success());

            Attempt badHostname = attempt(serverNormal, clientNoIdentity,
                    new String[]{TLS13}, new String[]{TLS13},
                    new String[]{C13}, new String[]{C13},
                    ClientAuth.NONE, true);
            check("wrongHostnameRejected", !badHostname.success());
            check("hostnameVerificationStayedOn",
                    badHostname.endpointIdentification());
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

### 11.3. Lệnh biên dịch và chạy

```bash
javac --release 17 TlsPolicyMatrixDemo.java
java TlsPolicyMatrixDemo server.p12 client.p12
```

`TLS_DEMO_PASSWORD` phải trùng password tạo keystore thử bằng keytool. Mã dùng `System.getenv` cho test-only password: dù xóa bản sao `char[]` bằng `Arrays.fill`, Java String từ môi trường không thể được xóa tuyệt đối; không coi đây là production secret manager.

### 11.4. Stdout chính xác trên OpenJDK 24

```text
serverPrivateKeyPresent=true
clientPrivateKeyPresent=true
serverCertificatePresent=true
clientCertificatePresent=true
tls13Supported=true
tls12Supported=true
tls13GcmSuiteSupported=true
tls12Gcm128SuiteSupported=true
tls12Gcm256SuiteSupported=true
defaultProtocolsNonempty=true
defaultCipherSuitesNonempty=true
disabledAlgorithmsPolicyPresent=true
needFlagTrue=true
needClearsWant=true
wantFlagTrue=true
wantClearsNeed=true
needCanBeRestored=true
tls13HandshakeSuccess=true
tls13Negotiated=true
tls13GcmCipherNegotiated=true
tls13ClientNotRequired=true
tls13PeerUnauthenticated=true
clientEndpointIdentificationOn=true
tls12HandshakeSuccess=true
tls12Negotiated=true
tls12GcmCipherNegotiated=true
wantWithoutCertificateSucceeds=true
wantFlagOnServer=true
wantPeerAbsent=true
needWithoutCertificateRejected=true
needFlagOnServer=true
needWithCertificateSucceeds=true
needClientPrincipalVerified=true
needProtocolTls13=true
noSharedProtocolRejected=true
noSharedCipherRejected=true
wrongHostnameRejected=true
hostnameVerificationStayedOn=true
```

**38/38 checks PASS.** Mỗi dòng được in qua `check(name, value)`, có ném `AssertionError` nếu bất kỳ điều kiện sai. Không dùng kết quả giả lập; đây là logs thực từ những TLS connections trên OpenJDK 24. Ciphersuite names được dùng cố định trong **fixture SunJSSE**, không khẳng định mọi JSSE provider đều hỗ trợ.

### 11.5. Giải thích kết quả theo nhóm

| Nhóm | Assertions | Kết luận |
| --- | --- | --- |
| Identity materials | `serverPrivateKeyPresent`, `clientPrivateKeyPresent`, `serverCertificatePresent`, `clientCertificatePresent` | Hai PKCS12 keystores test hợp lệ |
| Runtime metadata | `tls13Supported`, `tls12Supported`, `tls13GcmSuiteSupported`, `tls12Gcm128SuiteSupported`, `tls12Gcm256SuiteSupported` | SunJSSE đang hỗ trợ tên protocols/suites thử |
| Default & security policy | `defaultProtocolsNonempty`, `defaultCipherSuitesNonempty`, `disabledAlgorithmsPolicyPresent` | Có defaults và disabled algorithms property |
| Setter semantics | `needFlagTrue`, `needClearsWant`, `wantFlagTrue`, `wantClearsNeed`, `needCanBeRestored` | NEED và WANT không phải hai boolean độc lập |
| TLS 1.3 | `tls13HandshakeSuccess`, `tls13Negotiated`, `tls13GcmCipherNegotiated` | Đã handshake thật TLS 1.3/AES-GCM |
| TLS 1.3 server-auth | `tls13ClientNotRequired`, `tls13PeerUnauthenticated`, `clientEndpointIdentificationOn` | Không yêu cầu client cert, nhưng client kiểm tra hostname |
| TLS 1.2 | `tls12HandshakeSuccess`, `tls12Negotiated`, `tls12GcmCipherNegotiated` | Đã handshake thật TLS 1.2/ECDHE_RSA AES-GCM |
| WANT client cert | `wantWithoutCertificateSucceeds`, `wantFlagOnServer`, `wantPeerAbsent` | Client không có cert vẫn handshake được |
| NEED client cert | `needWithoutCertificateRejected`, `needFlagOnServer` | Không có client cert là thất bại |
| NEED + trusted client | `needWithCertificateSucceeds`, `needClientPrincipalVerified`, `needProtocolTls13` | mTLS xác minh certificate client và kết nối thành công |
| Không có giao nhau | `noSharedProtocolRejected`, `noSharedCipherRejected` | Protocol mismatch và suite mismatch đều fail |
| Hostname mismatch | `wrongHostnameRejected`, `hostnameVerificationStayedOn` | Client từ chối SAN không khớp, không tắt endpoint check |

### 11.6. Cách thử nghiệm tránh kết luận sai

Trong TLS 1.3, một số lỗi client-auth có thể được báo cho client **sau** bước mà một bên xem `startHandshake()` đã hoàn thành. Fixture trao đổi byte `65`/`66` giữa hai phía và chỉ đánh dấu success khi **cả server và client** đã thực sự trao đổi dữ liệu và hoàn thành. Điều này tránh biến “client không ném exception ngay tại startHandshake” thành false positive.

Case hostname sai dùng layered `SSLSocket` với transport thực tới `127.0.0.1` nhưng tên identity cần xác minh là `wrong.example`. Certificate test không có SAN đó, nên client bị từ chối **mà không tắt HTTPS endpoint identification**.

Mỗi attempt tạo một server socket cục bộ, dùng port ephemeral, timeouts và một executor; sockets được đóng và executor shut down. Các lỗi bắt được trong negative tests là expected; assertion vẫn kiểm tra kết nối **không** thành công.

### 11.7. Giới hạn fixture

- Chứng chỉ tự ký phát sinh trong test, không kiểm tra public CA chain, OCSP/CRL, expiry/rotation.
- SunJSSE OpenJDK 24 được kiểm thử; một JDK/FIPS provider khác có suites/disabledAlgorithms policy khác.
- TLS1.3 và TLS1.2 dùng single-suite allowlist **để minh họa**, không phải lời khuyên đóng băng production cipher list.
- Không kiểm thử TLS renegotiation, 0-RTT, session resumption, TLS exporters, ALPN, SNI-specific multi-tenancy, TCP load lớn, DTLS hay QUIC.
- Không triển khai web auth; mTLS chỉ kiểm tra peer certificate.
- Không triển khai private key storage production, HSM, PKCS#11 hay reloading cert trong tiến trình.
- Không thử bật giao thức yếu; không sửa security properties.

## 12. Troubleshooting khi TLS handshake không thành công

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `protocol_version` hoặc `handshake_failure` | Không có protocol chung | Đối chiếu enabled protocols của **hai đầu** |
| `no cipher suites in common` | Không có suite chung hoặc suite bị disable | Kiểm tra suite/protocol/provider/security policy |
| `PKIX path building failed` | Peer cert không được tin | Sửa CA/truststore chain, không trust-all |
| `No subject alternative names matching...` | Hostname/IP không khớp SAN | Cấp cert có SAN đúng URL, không bypass |
| `certificate_required` | Server NEED, client không có cert | Client KeyManager/private key/cert |
| `bad_certificate` / `unknown_ca` | Peer cert bị từ chối theo trust policy | Kiểm tra chain/EKU/issuer/validity |
| WANT vẫn chưa có peer principal | Client không gửi cert | Đây là tình huống hợp lệ trong WANT |
| NEED mà thiếu cert vẫn vào HTTP | Flag chưa được áp hoặc TLS terminate upstream | Xác nhận SSLParameters và TLS boundary |
| Có mTLS nhưng API trả 403 | TLS thành công, app authZ từ chối | Kiểm tra principal mapping/roles |
| TLS1.3 thành công, TLS1.2 thất bại | Server TLS1.2 suite/cert/key constraints | Thử TLS1.2-specific suites được phép |
| TLS1.2 thành công, TLS1.3 thất bại | Client profile, signature algorithms, suite mismatch | Kiểm tra provider và TLS1.3 support |
| `getSupportedCipherSuites` có suite nhưng handshake fail | Supported chưa có nghĩa enabled/allowed | Kiểm tra disabledAlgorithms và actual negotiated |
| Một bên báo success, bên kia close | TLS alert sau một pha handshake | Trao đổi dữ liệu hai phía, kiểm tra logs |
| Port connect được nhưng HTTPS không phản hồi | TLS handshake fail trước HTTP | Dò TLS trust/protocol/cert, không chỉ xem HTTP 500 |
| Sau JDK upgrade, ciphers thay đổi | Security defaults thay đổi | Regression test trên JDK/provider mục tiêu |

**Không hardcode exception message để quyết định “client thiếu cert”** trong production; mTLS fail do nhiều nguyên nhân khác nhau. Dùng JSSE diagnostics trong test isolated, ví dụ `-Djavax.net.debug=ssl:handshake`, nhưng logs có thể chứa certificate metadata; không bật chi tiết nhạy cảm trên production traffic.

## 13. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Dùng `SSLContext.getInstance("TLS")` rồi nghĩ xong TLS config | Chưa có key/trust managers và per-socket parameters | Init đúng context, áp SSLParameters |
| Coi `getSupportedSSLParameters` là security allowlist | Có thể gồm legacy/disabled choices | Xem defaults và security policy |
| Chỉ setProtocols ở client | Server có thể không có protocol chung | Kiểm thử cả hai endpoints |
| Bật TLSv1.0/TLSv1.1 để sửa handshake | Hạ mức an toàn | Nâng client, giữ TLS1.2/1.3 |
| Coi TLS1.3 suite name như TLS1.2 | Sai authentication/key exchange semantics | Phân biệt theo RFC TLS1.3 |
| Dùng TLS1.2 cipher suite cho TLS1.3-only | Không có common suite tương thích | Profile đúng theo TLS version |
| Hardcode cipher suite không được provider hỗ trợ | Handshake fail/IllegalArgumentException | Check supported và test thực |
| Vô hiệu hóa `jdk.tls.disabledAlgorithms` | Mở lại crypto yếu | Giữ JDK security policy |
| Coi WANT là bắt buộc chứng chỉ client | WANT cho phép không có client cert | Dùng NEED nếu bắt buộc |
| Gọi setWant sau setNeed rồi nghĩ NEED vẫn true | Flags loại trừ nhau | Chọn một policy |
| NEED nhưng server không trust client cert | Handshake fail | Server TrustManagerFactory phù hợp |
| Client chỉ có truststore mà không có private key | Không trình client cert được | Client KeyManagerFactory |
| Server không có PrivateKeyEntry | Không xác thực server | Keystore có private key + cert chain |
| Tắt hostname verification cho self-signed test | Dễ bị MITM | SAN đúng và trust cert test rõ ràng |
| Trust-all X509TrustManager | Tin bất kỳ attacker certificate | Trust CA/cert theo policy |
| Coi verified peer DN là quyền admin | Không có authorization binding | App principal mapping + authZ |
| Dùng low-level SSLSocket quên endpoint identification | Có trust chain nhưng chấp nhận host sai | `setEndpointIdentificationAlgorithm("HTTPS")` |
| Coi START handshake client=success dù server đã từ chối | TLS alerts có thể đến ở pha sau | Kiểm tra handshake và I/O cả hai phía |
| Kiểm tra chỉ tên suite requested | Chưa biết negotiated suite | `SSLSession.getCipherSuite()` |
| Log private keys/password/cert chain đầy đủ | Lộ secrets | Sanitized metrics/logging |
| Thay file PKCS12 rồi nghĩ SSLContext tự hot reload | Key material đã init riêng | Certificate rotation strategy |
| Dùng HttpsParameters setters deprecated | API legacy | Dùng SSLParameters/setSSLParameters |
| Mở TLS test server trên mọi interface | Rò dịch vụ local | Bind `127.0.0.1` |
| Chỉ test TLS, quên body/auth/rate limits | TLS không bảo vệ HTTP business layer | Security policies các tầng |

## 14. Checklist an toàn cho cấu hình TLS thực

1. Xác định TLS terminate ở đâu: ứng dụng, gateway, load balancer hay service mesh.
2. Chọn TLSv1.3/TLSv1.2 theo policy; không mở lại SSLv3/TLS1.0/TLS1.1.
3. Dùng `SSLContext` đã init identity/trust managers rõ ràng, không dựa vào config vô hình.
4. Xác minh `getDefaultSSLParameters` và `getSupportedSSLParameters` trên JDK/provider thực.
5. Cấu hình `SSLParameters.setProtocols` và nếu cần `setCipherSuites`, không dùng tên suite từ tutorial cũ.
6. Không bypass `jdk.tls.disabledAlgorithms`/`jdk.certpath.disabledAlgorithms`.
7. Có cert server SAN đúng hostname/IP và EKU/certificate profile phù hợp.
8. Client xác minh cert chain **và** endpoint identity.
9. Chọn NONE/WANT/NEED client authentication theo contract nghiệp vụ.
10. Nếu NEED, server có TrustManagers tin đúng client CA/certs, client có KeyManagers chứa private key/cert.
11. App kiểm tra quyền business riêng dù TLS peer identity đã xác minh.
12. Đảm bảo SSLParameters áp **trước** handshake; không cho phép requests qua connection đã không đúng TLS policy.
13. Sau handshake, lấy `SSLSession.getProtocol/getCipherSuite` để quan sát thực tế.
14. Test cả thành công và thất bại: version mismatch, suite mismatch, cert thiếu, trust lỗi, SAN sai.
15. Kiểm soát timeouts, memory, thread pool, max body, max connections và slow client.
16. Không log secrets hoặc TLS debug chi tiết trên production traffic.
17. Có keystore/secret manager permissions, certificate renewal/rotation/revocation policies.
18. Test lại sau JDK patch, security provider change, FIPS mode change và gateway update.

## 15. Bài tập thực hành

**Bài 1 — Supported vs enabled:** In `getSupportedSSLParameters().getProtocols()` và `getDefaultSSLParameters().getProtocols()`. So sánh; giải thích vì sao supported chưa đủ để kết luận usable.

**Bài 2 — Chỉ TLSv1.3:** Trong một scenario, đặt server/client chỉ TLSv1.3 và `TLS_AES_128_GCM_SHA256`. Sau handshake xác minh `SSLSession.getProtocol`/`getCipherSuite`.

**Bài 3 — Chỉ TLSv1.2:** Dùng `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`; kiểm tra cipher và protocol. Không dùng suite TLS1.3 trong TLS1.2-only scenario.

**Bài 4 — Protocol mismatch:** Server chỉ TLSv1.3, client chỉ TLSv1.2 nhưng có suites được hỗ trợ ở cả hai versions. Giải thích vì sao vẫn không có TLS session.

**Bài 5 — Cipher mismatch:** Giữ TLSv1.2 cho cả hai nhưng cho server một AES128-GCM suite và client chỉ AES256-GCM suite; kiểm tra handshake fail vì không có suite chung.

**Bài 6 — WANT client cert:** Server có TrustManager tin cert thử nghiệm nhưng `setWantClientAuth(true)`; client không cung cấp cert. Vì sao vẫn có TLS session nhưng `getPeerPrincipal` không có identity?

**Bài 7 — NEED client cert:** Chuyển sang `setNeedClientAuth(true)` và thử client không có keypair. Định nghĩa expected failure mà không hardcode exception message.

**Bài 8 — NEED có certificate:** Cho client `KeyManagerFactory` từ `client.p12`, server tin `clientCert`; xác minh peer principal. Sau đó thêm bước authorization riêng.

**Bài 9 — Hostname:** Giữ transport kết nối 127.0.0.1 nhưng yêu cầu danh tính `wrong.example`; client dùng `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` và phải từ chối cert SAN sai.

**Bài 10 — Cipher suites và providers:** Chạy cùng fixture với JDK khác; liệt kê supported suites, đối chiếu defaults và security properties. Không bật suites yếu để đạt output giống hệt.

**Bài 11 — HttpsConfigurator:** Chuyển profile `SSLParameters` vào `HttpsServer.setHttpsConfigurator`. Tránh setters deprecated trực tiếp trên HttpsParameters. Test một HTTPS endpoint thật bằng HttpClient có trust đúng.

**Bài 12 — Production profile:** Viết test plan mTLS/one-way + certificate rotation + revocation + permission mapping + gateway TLS termination; phân biệt transport-level và application-level checks.

## 16. Câu hỏi tự kiểm tra

**1. `SSLContext` khác `SSLParameters` thế nào?** Context giữ state TLS và key/trust managers; Parameters chọn protocols/ciphers/client-auth cho endpoint/connection.

**2. `getSupportedSSLParameters` có cho biết suites đang negotiated không?** Không; muốn biết negotiated dùng `SSLSession` sau handshake.

**3. `getDefaultSSLParameters` có bất biến giữa JDK releases không?** Không, phụ thuộc provider/version/security policy.

**4. TLSv1.3 và TLSv1.2 dùng tên suite giống nhau không?** Không hoàn toàn; TLS1.3 suites không chứa key exchange/authentication trong tên như TLS1.2.

**5. `TLS_AES_128_GCM_SHA256` là TLS1.3 hay TLS1.2 suite trong fixture?** TLS 1.3.

**6. `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` là ví dụ gì?** TLS 1.2, ECDHE RSA authentication, AES-GCM.

**7. App setter có thể vượt `jdk.tls.disabledAlgorithms` không?** Không, policy vẫn chặn handshake.

**8. Không có protocol chung thì có TLS session không?** Không, handshake fail.

**9. Không có cipher suite chung thì sao?** Handshake fail dù protocol chung.

**10. `setWantClientAuth(true)` có bắt buộc client cert không?** Không.

**11. `setNeedClientAuth(true)` yêu cầu gì?** Client phải trình cert đáng tin, server có trust policy đúng.

**12. Gọi `setWantClientAuth(true)` sau `setNeedClientAuth(true)` thì sao?** Want thay trạng thái need, không còn bắt buộc client cert.

**13. Server mTLS có cần TrustManager không?** Có, để xác minh client cert chain.

**14. Client mTLS có cần KeyManager không?** Có, nếu phải trình private key/cert identity.

**15. Client tin server cert nhưng SAN sai, kết quả?** HTTPS endpoint verification phải từ chối.

**16. Low-level SSLSocket có mặc nhiên kiểm tra HTTPS hostname?** Không được giả định; set endpoint identification algorithm thích hợp.

**17. `SSLSession.getProtocol()` trả HTTP/2 hay TLSv1.3?** TLS version, ví dụ TLSv1.3.

**18. mTLS peer CN có tự là role admin không?** Không, vẫn cần application authorization.

**19. TLS handshake fail có HTTP 401 không?** Thường chưa có HTTP response.

**20. Bộ 38 checks đủ chứng nhận production-ready không?** Không, chỉ kiểm chứng các kịch bản fixture trên JDK/provider đã test.

## Nguồn chuẩn còn hiệu lực

- [Oracle Java SE 26 — SSLParameters](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): get/setProtocols, get/setCipherSuites, need/want clientAuth, endpoint identification.
- [Oracle Java SE 26 — SSLContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLContext.html): getDefaultSSLParameters, getSupportedSSLParameters, key/trust managers và init.
- [Oracle Java SE 26 — SSLSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocket.html): setSSLParameters, startHandshake, SSLSession.
- [Oracle Java SE 26 — SSLServerSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLServerSocket.html): SSLParameters cho accepted sockets, want/need semantics.
- [Oracle Java SE 26 — SSLSession](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSession.html): negotiated protocol/cipher/peer principal.
- [Oracle Java SE 26 — SSLEngine](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLEngine.html): TLS nonblocking engine và parameters.
- [Oracle Java SE 26 — HttpsConfigurator](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html): TLS connection configuration.
- [Oracle Java SE 26 — HttpsParameters](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsParameters.html): setSSLParameters, deprecated direct setters.
- [Oracle Java SE 26 — Deprecated List](https://docs.oracle.com/en/java/javase/26/docs/api/deprecated-list.html): HttpsParameters direct setters deprecated since 23.
- [Oracle Java SE 26 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html): security properties, TLS interoperability, client cert.
- [Oracle Java SE 26 — JDK Providers](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): SunJSSE supported protocols/suites, enabled/disabled policy.
- [Oracle Java SE 26 — KeyStore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html): PKCS12 private keys và trusted certificates.
- [Oracle Java SE 26 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): endpoint identity.
- [Oracle Java SE 26 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): peer certificate validation.
- [Oracle Java SE 26 — keytool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html): tạo certificates thử.
- [IETF RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): version/cipher suite/handshake rules.
- [IETF RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246): TLS 1.2 legacy specification used for understanding interop, **không** khuyến nghị protocol TLS 1.0/1.1.

**Ghi nhớ:** Với Java hiện hành, hãy chọn `SSLParameters.setProtocols`, `setCipherSuites` và **một** trong `setWantClientAuth`/`setNeedClientAuth`, áp trên socket/engine/configurator **trước handshake**, và kiểm chứng kết quả bằng `SSLSession`. `Supported` không đồng nghĩa `enabled`; `jdk.tls.disabledAlgorithms` có thể cấm cả khi app bật. **WANT** không yêu cầu cert bắt buộc; **NEED** phải có client private key/cert **và** server trust đúng. Client phải tin server certificate và kiểm tra hostname/SAN. Không áp dụng các TLS/HTTPS APIs deprecated hoặc bỏ kiểm tra an toàn chỉ để kết nối thành công. Bài tập đã dùng 38 phép kiểm thử thật qua JSSE sockets và JDK 17+-compatible code.
