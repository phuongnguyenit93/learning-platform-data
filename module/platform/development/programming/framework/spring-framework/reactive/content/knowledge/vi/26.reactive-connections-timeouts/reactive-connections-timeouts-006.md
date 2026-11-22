# TLS, chứng chỉ, proxy và phân giải tên miền với Spring WebClient

## 1. Mục tiêu: kết nối HTTPS an toàn và chẩn đoán được lỗi mạng

`WebClient` cung cấp API HTTP reactive, nhưng việc mở socket, phân giải tên miền, đi qua proxy và thực hiện TLS handshake được giao cho HTTP connector bên dưới. Trong ứng dụng Spring Boot dùng `spring-boot-starter-webflux`, connector thường được auto-configure là Reactor Netty nếu dependency này có trên classpath.

Một request HTTPS chỉ thành công khi nhiều bước liên tiếp đều đúng:

1. **DNS** tìm địa chỉ IP cho hostname.
2. **Connection pool/TCP** cung cấp kết nối hoặc mở kết nối tới server/proxy.
3. **Proxy**, nếu được cấu hình, chấp nhận kết nối và thiết lập tunnel phù hợp.
4. **TLS handshake** thương lượng phiên mã hóa, xác thực certificate chain và hostname của server.
5. Nếu server yêu cầu **mutual TLS (mTLS)**, client cũng trình certificate và chứng minh đang sở hữu private key tương ứng.
6. Sau khi kênh bảo mật sẵn sàng, WebClient mới gửi HTTP request và decode response.

Một lỗi ở từng bước có nguyên nhân và cách sửa khác nhau. Ví dụ, `UnknownHostException` là vấn đề phân giải tên miền; `ConnectTimeoutException` là vấn đề thiết lập kết nối; `SSLHandshakeException` thường liên quan certificate, trust hoặc TLS negotiation; HTTP 407 thường liên quan proxy authentication; HTTP 401/403 thường liên quan xác thực/phân quyền tại dịch vụ đích.

Bài học này dùng Spring Framework 6.2, Spring Boot 3.3.x, Java 17+ và Reactor Netty 1.1.x làm nền tảng. Sau bài này, bạn có thể:

- Giải thích truststore, keystore, certificate chain, SAN, SNI, hostname verification và mTLS.
- Cấu hình WebClient dùng CA nội bộ hoặc client certificate.
- Kết nối qua HTTP proxy, dùng proxy authentication và thiết lập bypass hosts.
- Hiểu DNS resolver bất đồng bộ của Reactor Netty, cache TTL và ảnh hưởng của connection pool.
- Cấu hình timeout riêng cho pool acquire, DNS, TCP connect, proxy connect, TLS handshake và response.
- Phân loại lỗi theo từng giai đoạn và kiểm tra bằng công cụ dòng lệnh.
- Kiểm thử TLS trust và hostname verification bằng MockWebServer.

## 2. WebClient kết nối HTTPS qua những lớp nào?

`WebClient` không tự triển khai TCP hay TLS. Nó gọi một `ClientHttpConnector`. Spring hỗ trợ Reactor Netty, JDK HttpClient, Jetty Reactive HttpClient, Apache HttpComponents và các connector khác. Cấu hình SSL, proxy và DNS vì vậy phụ thuộc connector đang được sử dụng.

Với Reactor Netty, luồng kết nối có thể hình dung như sau:

```text
WebClient request
      |
      v
Connection pool
      |
      +---- có connection phù hợp -> tái sử dụng
      |
      +---- chưa có connection
                 |
                 v
            DNS resolver
                 |
                 v
              TCP connect
                 |
                 +---- đi thẳng tới origin
                 |
                 +---- hoặc kết nối tới HTTP proxy
                              |
                              v
                         HTTP CONNECT
                              |
                              v
                         TLS handshake
                              |
                              v
                 Verify certificate chain + hostname
                              |
                    optional client certificate (mTLS)
                              |
                              v
                       HTTP request/response
```

Thứ tự chi tiết thay đổi theo direct connection hay proxy, nhưng cần phân biệt các lớp sau:

| Lớp | Câu hỏi cần trả lời | Lỗi thường gặp |
|---|---|---|
| Connection pool | Có connection rảnh để dùng không? | `PoolAcquireTimeoutException` |
| DNS | Hostname phân giải thành IP nào? | `UnknownHostException`, DNS timeout |
| TCP | Có mở được socket tới peer không? | `ConnectException`, `ConnectTimeoutException` |
| Proxy | Proxy có nhận kết nối, xác thực và mở tunnel không? | HTTP 407, proxy connect timeout, tunnel failure |
| TLS | Certificate có đáng tin và đúng hostname không? | `SSLHandshakeException`, `CertificateException` |
| HTTP | Dịch vụ đích trả status nào? | 401, 403, 404, 429, 5xx |
| Decode | Response body có đúng media type/schema không? | `DecodingException` |

Nếu dùng `WebClient` với connector khác Reactor Netty, không sao chép máy móc API `HttpClient` hoặc `ProxyProvider`; hãy cấu hình theo thư viện HTTP client thực tế.

## 3. TLS, certificate chain và danh tính của server

TLS cung cấp ba đặc tính chính:

- **Confidentiality**: mã hóa dữ liệu trên đường truyền.
- **Integrity**: phát hiện dữ liệu bị sửa đổi trong quá trình truyền.
- **Peer authentication**: xác minh server mà client đang kết nối là server có danh tính phù hợp.

Khi gọi `https://api.example.com`, client nhận certificate của server. Client kiểm tra certificate chain có dẫn tới một trust anchor được tin cậy hay không, certificate còn hiệu lực không và certificate có nhận diện đúng hostname `api.example.com` hay không.

### 3.1. Certificate chain

Một chuỗi certificate thường gồm:

```text
Root CA (trust anchor)
      |
      v
Intermediate CA
      |
      v
Server/leaf certificate
      |
      v
api.example.com
```

Server thường gửi leaf certificate và các intermediate certificate cần thiết. Client có root CA hoặc trust anchor phù hợp trong truststore để kiểm tra chuỗi.

Các điều kiện quan trọng:

- Chữ ký của certificate phải hợp lệ.
- Chain phải dẫn tới trust anchor được client tin cậy.
- Certificate phải nằm trong khoảng `Not Before` / `Not After`.
- Extended Key Usage phải phù hợp với mục đích server authentication.
- Hostname phải khớp Subject Alternative Name (SAN).
- TLS protocol và cipher suite phải có lựa chọn chung được cả hai bên chấp nhận.

Chỉ nhìn thấy certificate trong trình duyệt hoặc có thể mở URL bằng `curl` trên máy cá nhân không chứng minh container Java có cùng truststore hoặc DNS/proxy configuration.

### 3.2. SAN và hostname verification

Hostname verification kiểm tra tên host trong URL có được certificate nhận diện hay không. Với HTTPS hiện đại, client nên dựa vào SAN (Subject Alternative Name), ví dụ:

```text
DNS:api.example.com
DNS:*.internal.example.com
IP:10.20.30.40
```

Certificate có SAN `api.example.com` có thể hợp lệ khi gọi `https://api.example.com`. Nếu gọi bằng `https://10.20.30.40`, certificate cần có SAN dạng IP tương ứng hoặc một cơ chế tên khác được xác minh đúng.

Certificate chain hợp lệ không đồng nghĩa hostname hợp lệ. Một certificate do CA đáng tin cấp cho `other.example.com` vẫn không chứng minh peer là `api.example.com`.

### 3.3. SNI là gì?

Server Name Indication (SNI) là thông tin hostname client gửi trong TLS handshake để server có thể chọn certificate phù hợp khi nhiều domain dùng chung một IP.

Reactor Netty mặc định dùng hostname từ remote URI làm SNI server name. SNI giúp server chọn certificate; hostname verification vẫn là bước kiểm tra riêng. Thay SNI không thay thế việc xác minh certificate identity.

Tránh đổi URL thành IP chỉ để né DNS. Làm vậy có thể khiến SNI và hostname verification không còn khớp certificate của dịch vụ.

## 4. Truststore và keystore khác nhau thế nào?

Hai khái niệm này có vai trò khác nhau:

| Thành phần | Chứa gì? | Dùng để làm gì? |
|---|---|---|
| Truststore | CA certificate hoặc trust anchor | Client quyết định certificate của server nào được tin cậy |
| Keystore | Private key và certificate chain của chính client/server | Client hoặc server chứng minh danh tính của mình khi được yêu cầu |

Với kết nối HTTPS thông thường, client chỉ cần truststore phù hợp. Nếu dịch vụ yêu cầu mTLS, client cần thêm keystore chứa client certificate và private key.

Các định dạng thường gặp:

- **PKCS12 (`.p12`, `.pfx`)**: thường chứa private key, certificate chain hoặc trust certificates.
- **JKS (`.jks`)**: định dạng keystore/truststore của Java.
- **PEM (`.pem`, `.crt`, `.key`)**: certificate và private key dưới dạng văn bản Base64 có header/footer; private key dùng với Netty cần định dạng được API hỗ trợ, thường là PKCS#8.

Không gửi private key của client cho server hoặc commit vào Git. Certificate công khai có thể được chia sẻ theo quy trình, nhưng private key phải được quản lý như secret.

## 5. Dùng CA nội bộ để xác minh server

Nếu server dùng certificate do CA nội bộ cấp, JVM có thể chưa tin CA đó. Cách chuẩn là đưa CA root/intermediate được tổ chức phê duyệt vào truststore mà WebClient sử dụng.

### 5.1. Dùng PEM certificate với Netty `SslContextBuilder`

```java
File internalCa = new File("/etc/app/certs/internal-root-ca.pem");

SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(internalCa)
        .build();

HttpClient httpClient = HttpClient.create()
        .secure(ssl -> ssl.sslContext(sslContext));

WebClient webClient = WebClient.builder()
        .baseUrl("https://api.internal.example")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

`trustManager(File)` nhận một file PEM chứa X.509 certificate collection dùng để xác minh certificate của peer. Ví dụ này tạo trust context dựa trên CA nội bộ.

Nếu ứng dụng phải gọi cả dịch vụ công khai lẫn dịch vụ nội bộ, hãy bảo đảm truststore chứa đầy đủ các CA cần thiết. Một truststore tự tạo chỉ có CA nội bộ có thể không còn tin các CA công khai mà JVM mặc định vốn tin. Có thể tạo truststore hợp nhất hoặc quản lý các WebClient có trust policy riêng cho từng nhóm dịch vụ.

### 5.2. Tạo truststore PKCS12

Có thể nhập CA vào truststore bằng `keytool`:

```bash
keytool -importcert \
  -alias internal-root-ca \
  -file internal-root-ca.pem \
  -keystore internal-truststore.p12 \
  -storetype PKCS12
```

Lệnh yêu cầu nhập password cho truststore và xác nhận certificate. Chỉ import certificate đã được xác minh fingerprint hoặc nhận qua kênh tin cậy.

Kiểm tra nội dung:

```bash
keytool -list -v \
  -keystore internal-truststore.p12 \
  -storetype PKCS12
```

Java có thể nạp truststore rồi tạo `TrustManagerFactory`:

```java
KeyStore trustStore = KeyStore.getInstance("PKCS12");

try (InputStream input = Files.newInputStream(
        Path.of("/etc/app/certs/internal-truststore.p12"))) {
    trustStore.load(input, trustStorePassword);
}

TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trustStore);

SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(trustManagers)
        .build();
```

`trustStorePassword` nên được lấy từ secret manager hoặc cơ chế secret của môi trường triển khai, không hardcode vào source code.

### 5.3. Khi nào dùng truststore mặc định của JVM?

Nếu dịch vụ dùng certificate chain công khai và truststore JVM đã có root CA tương ứng, có thể dùng cấu hình mặc định:

```java
HttpClient httpClient = HttpClient.create().secure();
```

Reactor Netty 1.1 bật hostname verification cho `secure()` và overload `secure(Consumer<SslContextSpec>)`. Không cần tạo truststore riêng chỉ để dùng HTTPS thông thường.

Nếu certificate chain không được tin cậy, hãy tìm đúng CA/intermediate hoặc kiểm tra server có gửi đủ chain không. Không dùng trust-all manager để làm biến mất lỗi certificate.

## 6. Mutual TLS (mTLS): client cũng phải trình certificate

Trong HTTPS một chiều thông thường, client xác minh server. Với mTLS, server cũng yêu cầu client trình certificate để xác thực danh tính của client.

```text
Client                              Server
  |                                   |
  |------ ClientHello --------------->|
  |<----- Server certificate ---------|
  |------ Verify server certificate   |
  |<----- CertificateRequest ---------|
  |------ Client certificate -------->|
  |------ CertificateVerify --------->|
  |<----- Handshake complete -------->|
  |------ HTTP request -------------->|
```

Server cần tin CA đã cấp client certificate. Client vẫn cần tin CA đã cấp server certificate. Đây là hai trust decision riêng biệt.

### 6.1. Cấu hình client certificate dạng PEM

```java
SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(new File("/etc/app/certs/server-ca.pem"))
        .keyManager(
                new File("/etc/app/certs/client-chain.pem"),
                new File("/etc/app/certs/client-key.pk8"))
        .build();

HttpClient httpClient = HttpClient.create()
        .secure(ssl -> ssl.sslContext(sslContext));

WebClient webClient = WebClient.builder()
        .baseUrl("https://partner.example.com")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

`client-chain.pem` chứa certificate chain của client. `client-key.pk8` là private key PKCS#8 tương ứng. Nếu private key được mã hóa, dùng overload `keyManager` có password theo API Netty đang sử dụng.

### 6.2. Cấu hình mTLS bằng PKCS12

```java
KeyStore clientKeyStore = KeyStore.getInstance("PKCS12");

try (InputStream input = Files.newInputStream(clientKeyStorePath)) {
    clientKeyStore.load(input, clientKeyStorePassword);
}

KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagers.init(clientKeyStore, clientKeyStorePassword);

SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(serverTrustManagerFactory)
        .keyManager(keyManagers)
        .build();
```

Keystore phải chứa private key entry và certificate chain của client. Nếu chỉ có certificate công khai mà không có private key tương ứng, client không thể chứng minh quyền sở hữu certificate trong handshake.

### 6.3. Những lỗi mTLS thường gặp

- Không gửi client certificate dù server yêu cầu.
- Certificate client đã hết hạn.
- Private key không khớp certificate.
- Server không tin CA đã cấp client certificate.
- Client gửi chain thiếu intermediate.
- EKU/key usage không cho phép mục đích client authentication.
- Certificate được gửi nhưng không được cấp quyền cho API/tenant tương ứng.

HTTP 401/403 sau khi TLS handshake thành công thường là lỗi ở tầng HTTP authorization hoặc application policy, không nhất thiết là lỗi mTLS.

## 7. Hostname verification: bảo vệ danh tính của endpoint

Reactor Netty 1.1 có các overload SSL với hành vi khác nhau:

- `HttpClient.secure()` dùng SSL mặc định và bật hostname verification.
- `HttpClient.secure(Consumer<SslContextSpec>)` cũng bật hostname verification.
- `HttpClient.secure(SslProvider)` nhận một provider được dựng sẵn; hostname verification không tự được bật trong overload này.

Nếu tự dựng `SslProvider`, phải gắn hostname verification configurator:

```java
SslProvider sslProvider = SslProvider.builder()
        .sslContext(SslContextBuilder.forClient()
                .trustManager(new File("/etc/app/certs/internal-ca.pem")))
        .handlerConfigurator(
                HttpClientSecurityUtils.HOSTNAME_VERIFICATION_CONFIGURER)
        .build();

HttpClient httpClient = HttpClient.create()
        .secure(sslProvider);
```

Nếu dùng overload `secure(SslProvider)` mà quên configurator, certificate chain có thể được tin cậy nhưng hostname không được xác minh như mong đợi.

### Không tắt xác minh để sửa lỗi

Không dùng các cách sau trong production:

- `InsecureTrustManagerFactory.INSTANCE`.
- Trust manager luôn trả certificate hợp lệ.
- Tắt endpoint identification/hostname verification.
- Chấp nhận mọi certificate chỉ vì môi trường là staging.
- Gọi IP để bỏ qua mismatch hostname.

Những cách này làm mất khả năng xác minh server identity và có thể mở đường cho man-in-the-middle. Hãy sửa certificate SAN, trust chain, URL hostname, SNI hoặc CA configuration.

### Phân biệt trust chain, SNI và hostname verification

| Cơ chế | Câu hỏi | Không thay thế điều gì? |
|---|---|---|
| Trust chain validation | Ai cấp certificate và CA đó có đáng tin không? | Không chứng minh hostname khớp |
| SNI | Client muốn server trình certificate cho hostname nào? | Không xác minh certificate |
| Hostname verification | Certificate có nhận diện đúng host trong URL không? | Không tự tạo trust anchor |
| mTLS | Client có certificate được server chấp nhận không? | Không thay xác thực quyền ở HTTP/API |

## 8. HTTP proxy và HTTPS CONNECT tunnel

Proxy là một hop mạng nằm giữa WebClient và dịch vụ đích. Trong môi trường doanh nghiệp, proxy có thể được dùng để kiểm soát outbound traffic, audit hoặc truy cập Internet.

Với HTTP proxy, Reactor Netty hỗ trợ `ProxyProvider`:

```java
HttpClient httpClient = HttpClient.create()
        .proxy(spec -> spec
                .type(ProxyProvider.Proxy.HTTP)
                .host("proxy.internal.example")
                .port(8080)
                .nonProxyHosts("localhost|127\\.0\\.0\\.1")
                .connectTimeoutMillis(10_000));
```

`nonProxyHosts` là regular expression cho hostname được truy cập trực tiếp. Hãy cấu hình cẩn thận để không vô tình bypass proxy đối với các host cần được kiểm soát.

### 8.1. HTTPS qua HTTP proxy

Khi gọi HTTPS qua HTTP proxy, client thường yêu cầu proxy mở tunnel bằng phương thức `CONNECT` tới host/port đích. Sau khi tunnel được thiết lập, TLS handshake được thực hiện với endpoint đích qua tunnel đó.

```text
WebClient
   |
   | TCP
   v
HTTP proxy
   |
   | CONNECT api.example.com:443
   v
Tunnel tới origin
   |
   | TLS handshake với api.example.com
   v
HTTPS API
```

Proxy có thể thấy hostname/port đích và metadata mạng. Nếu proxy chỉ tạo CONNECT tunnel, nội dung HTTP bên trong TLS được mã hóa giữa client và origin.

Một số proxy doanh nghiệp thực hiện TLS inspection: proxy kết thúc TLS từ client rồi tạo một TLS connection khác tới origin. Trong trường hợp đó client nhìn thấy certificate do CA nội bộ của tổ chức cấp. Chỉ cài CA inspection khi có chính sách và xác nhận từ bộ phận quản trị bảo mật.

Reactor Netty sử dụng CONNECT cho HTTP proxy tunnel; một số proxy không hỗ trợ CONNECT trong mọi chế độ hoặc cần được cấu hình riêng. Kiểm tra tài liệu proxy khi kết nối tunnel thất bại.

### 8.2. Proxy authentication

Proxy authentication khác origin authentication:

- `Proxy-Authorization` xác thực client với proxy.
- `Authorization` xác thực client với API đích.

Có thể cấu hình username/password của HTTP proxy bằng `ProxyProvider`:

```java
String proxyUser = System.getenv("OUTBOUND_PROXY_USER");
String proxyPassword = System.getenv("OUTBOUND_PROXY_PASSWORD");

HttpClient httpClient = HttpClient.create()
        .proxy(spec -> spec
                .type(ProxyProvider.Proxy.HTTP)
                .host("proxy.internal.example")
                .port(8080)
                .username(proxyUser)
                .password(ignoredUsername -> proxyPassword)
                .connectTimeoutMillis(10_000));
```

API `password` nhận một function cung cấp password theo username. Lấy credential từ secret manager/environment; không hardcode vào code, log hoặc exception message.

HTTP 407 Proxy Authentication Required thường liên quan proxy credentials hoặc proxy policy. HTTP 401/403 từ origin là một lớp khác.

### 8.3. Proxy và DNS của hostname đích

Khi đi qua proxy, cần biết bên nào phân giải hostname đích:

- Client có thể phân giải host rồi kết nối tới địa chỉ tương ứng theo connector/proxy configuration.
- Proxy có thể nhận hostname trong CONNECT và tự phân giải từ mạng của proxy.
- Nếu có custom resolver, hành vi có thể thay đổi.

Vì vậy, khi DNS trên máy developer thành công nhưng container qua proxy vẫn lỗi, hãy kiểm tra DNS tại đúng nơi đang phân giải hostname: runtime của ứng dụng, proxy hoặc cả hai. Không giả định mọi proxy dùng cùng DNS view với ứng dụng.

## 9. DNS resolution trong Reactor Netty

Reactor Netty `HttpClient` mặc định dùng Netty domain name resolver để phân giải hostname bất đồng bộ. Cách này khác JVM resolver truyền thống có thể thực hiện lookup blocking.

Ví dụ giới hạn thời gian cho mỗi DNS query:

```java
HttpClient httpClient = HttpClient.create()
        .resolver(spec -> spec.queryTimeout(Duration.ofSeconds(2)));
```

Reactor Netty cho phép tùy chỉnh DNS cache:

```java
HttpClient httpClient = HttpClient.create()
        .resolver(spec -> spec
                .queryTimeout(Duration.ofSeconds(2))
                .cacheMaxTimeToLive(Duration.ofSeconds(60))
                .cacheMinTimeToLive(Duration.ofSeconds(5))
                .cacheNegativeTimeToLive(Duration.ofSeconds(2)));
```

Ý nghĩa:

| Cấu hình | Tác dụng |
|---|---|
| `queryTimeout` | Thời gian tối đa cho mỗi DNS query |
| `cacheMaxTimeToLive` | Giới hạn trên TTL của DNS record trong cache |
| `cacheMinTimeToLive` | Giới hạn dưới TTL của DNS record trong cache |
| `cacheNegativeTimeToLive` | TTL cache cho kết quả phân giải thất bại |

Theo tài liệu Reactor Netty 1.1.21, `queryTimeout` mặc định là 5 giây; cache min TTL mặc định là 0 và negative TTL mặc định là 0. Cache max TTL mặc định rất lớn (`Integer.MAX_VALUE` giây), nên nếu hệ thống cần cập nhật địa chỉ nhanh, hãy đặt policy có chủ đích.

### 9.1. Dùng JVM built-in resolver

Nếu cần dùng JVM resolver thay Netty resolver:

```java
HttpClient httpClient = HttpClient.create()
        .resolver(DefaultAddressResolverGroup.INSTANCE);
```

Đây là một lựa chọn tương thích, không phải mặc định cần thay thế. JVM built-in resolver có đặc điểm lookup khác với Netty asynchronous DNS resolver; hãy cân nhắc ảnh hưởng tới thread và latency trước khi chuyển.

### 9.2. Những yếu tố thường gây DNS failure

- Hostname sai hoặc không có record.
- DNS server trong container/Kubernetes không truy cập được.
- Search domain hoặc `/etc/resolv.conf` không như mong đợi.
- Split-horizon DNS: laptop và production resolve cùng hostname thành IP khác nhau.
- A record có nhưng AAAA record không hoạt động hoặc ngược lại.
- DNS cache giữ kết quả cũ hoặc cache negative result.
- Proxy resolve host đích bằng DNS view khác với client.
- Dịch vụ nội bộ chỉ tồn tại trong private DNS zone.

Không thay hostname bằng IP như cách sửa mặc định. Điều đó có thể làm SNI và hostname verification không khớp certificate.

## 10. DNS cache và connection pool là hai cơ chế khác nhau

DNS TTL quyết định thời gian một kết quả phân giải có thể được dùng lại trong resolver cache. Connection pool giữ các kết nối TCP đã được thiết lập để request sau có thể tái sử dụng.

Khi DNS record thay đổi:

1. Resolver có thể nhận IP mới sau khi cache hết TTL.
2. Connection TCP đang mở vẫn trỏ tới IP cũ.
3. Request tiếp theo có thể tái sử dụng connection cũ mà không cần DNS lookup mới.
4. Chỉ khi tạo connection mới, client mới cần phân giải và kết nối tới địa chỉ hiện tại.

Vì vậy, DNS TTL ngắn không tự đóng những connection đã được pool giữ lại.

Có thể giới hạn tuổi thọ connection:

```java
ConnectionProvider provider = ConnectionProvider.builder("partner")
        .maxConnections(100)
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .evictInBackground(Duration.ofSeconds(30))
        .build();

HttpClient httpClient = HttpClient.create(provider);
```

Khi đặt `maxIdleTime`, nên chọn giá trị không lớn hơn idle timeout mà server/proxy cho phép để giảm nguy cơ tái sử dụng connection đã bị peer đóng. `maxLifeTime` giúp connection được thay mới theo thời gian, hữu ích khi endpoint IP được cân bằng hoặc xoay vòng.

Nếu tự tạo `ConnectionProvider`, quản lý vòng đời và dispose nó khi ứng dụng dừng. Với global Reactor Netty resources mặc định, nhiều client có thể chia sẻ event loop và connection resources; đây thường là lựa chọn phù hợp cho ứng dụng Spring.

## 11. Timeout: cấu hình từng giai đoạn riêng biệt

Một timeout tổng không cho biết chính xác request bị chậm ở đâu. Reactor Netty có các timeout theo giai đoạn:

| Giai đoạn | API | Mặc định trong Reactor Netty 1.1.21 theo tài liệu |
|---|---|---|
| Chờ connection từ pool | `pendingAcquireTimeout` | 45 giây |
| DNS query | `queryTimeout` | 5 giây cho mỗi query |
| TCP connect | `CONNECT_TIMEOUT_MILLIS` | 30 giây |
| TLS handshake | `handshakeTimeout` | 10 giây |
| Proxy connect | `connectTimeoutMillis` của proxy | 10 giây |
| Response read interval | `responseTimeout` | Không đặt mặc định |

Các timeout có ý nghĩa khác nhau:

- Pool acquire timeout xảy ra trước khi có connection để gửi request.
- DNS timeout đo thời gian phân giải hostname.
- Connect timeout đo thời gian mở kết nối TCP.
- TLS handshake timeout đo thời gian hoàn tất TLS handshake.
- Response timeout giới hạn khoảng thời gian giữa các lần đọc dữ liệu response ở tầng mạng; nó không nhất thiết là deadline tổng cho cả request.
- `Mono.timeout(Duration)` có thể đặt deadline cho toàn publisher từ lúc subscribe đến khi hoàn tất, bao gồm nhiều giai đoạn.

### 11.1. Cấu hình kết hợp

```java
ConnectionProvider provider = ConnectionProvider.builder("catalog")
        .maxConnections(80)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .build();

HttpClient httpClient = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
        .responseTimeout(Duration.ofSeconds(8))
        .resolver(spec -> spec.queryTimeout(Duration.ofSeconds(2)))
        .secure(ssl -> ssl
                .sslContext(Http11SslContextSpec.forClient())
                .handshakeTimeout(Duration.ofSeconds(10)));

WebClient webClient = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

Các giá trị là ví dụ khởi đầu, không phải một bộ timeout đúng cho mọi dịch vụ. Hãy dựa trên latency percentile, network topology, SLA và thời gian xử lý upstream.

### 11.2. Deadline tổng cho một use case

```java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(12));
```

Deadline tổng hữu ích khi use case cần giới hạn thời gian hoàn tất. Tuy nhiên, vẫn nên cấu hình timeout cụ thể cho DNS, connect, handshake và response để xác định nguyên nhân chậm.

### 11.3. Tránh timeout chồng lấn thiếu chủ đích

Ví dụ pool acquire timeout 2 giây, DNS query 2 giây, connect 5 giây, TLS handshake 10 giây và deadline tổng 4 giây sẽ khiến một số giai đoạn không thể dùng hết thời gian cấu hình riêng. Đây không sai về kỹ thuật, nhưng cần hiểu timeout tổng sẽ hủy publisher trước khi timeout chi tiết dài hơn phát sinh.

Hãy đặt deadline theo ngân sách thời gian của use case rồi phân bổ phần thời gian cho các bước bên trong.

## 12. Kết nối WebClient với Reactor Netty

Spring Framework cho phép cắm connector đã cấu hình vào WebClient:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(8));

WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.com")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

Trong Spring Boot, nên inject `WebClient.Builder` auto-configured khi muốn kế thừa codec configuration và shared resources của Boot. `WebClient.create()` tạo client trực tiếp và không nhận các customization đã được áp dụng cho builder auto-configured.

Ví dụ bean:

```java
@Configuration
public class PartnerClientConfiguration {

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
                .responseTimeout(Duration.ofSeconds(8));

        return builder
                .baseUrl("https://partner.example.com")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

Nếu cấu hình SSL, proxy hoặc DNS khác nhau giữa các dịch vụ, tạo client riêng cho từng trust policy/route. Tránh một client có credential hoặc trust policy quá rộng rồi dùng để gọi mọi hostname.

## 13. Chẩn đoán lỗi theo từng giai đoạn

### 13.1. Lỗi DNS

Triệu chứng:

```text
java.net.UnknownHostException: api.internal.example
```

Kiểm tra từ đúng container/VM đang chạy ứng dụng:

```bash
nslookup api.internal.example
```

Hoặc:

```bash
dig api.internal.example
```

Trên Linux, có thể kiểm tra:

```bash
getent hosts api.internal.example
cat /etc/resolv.conf
```

Đừng chỉ kiểm tra DNS trên máy laptop nếu ứng dụng chạy trong Kubernetes, Docker hoặc một subnet riêng.

### 13.2. Lỗi TCP connect

Triệu chứng có thể gồm:

```text
Connection refused
ConnectTimeoutException
No route to host
```

Kiểm tra:

- Host và port có đúng không?
- Security group, firewall, NetworkPolicy hoặc routing có chặn không?
- Dịch vụ có đang listen không?
- Ứng dụng đang kết nối trực tiếp hay qua proxy?
- Proxy host/port có truy cập được từ container không?

### 13.3. Lỗi TLS handshake

Một số thông báo thường gặp:

| Thông báo | Nguyên nhân cần kiểm tra |
|---|---|
| `PKIX path building failed` | Truststore không có CA phù hợp hoặc server thiếu intermediate |
| `unable to find valid certification path` | Không xây dựng được trust chain |
| `No subject alternative DNS name matching ...` | Hostname trong URL không khớp SAN |
| `certificate expired` | Certificate hết hạn hoặc thời gian hệ thống sai |
| `bad_certificate` | Client certificate không được server chấp nhận |
| `handshake_failure` | Protocol/cipher/client-auth policy không tương thích |
| `SSLHandshakeException` | Lỗi tổng quát trong handshake; cần đọc cause chain |

Có thể kiểm tra certificate chain và hostname bằng OpenSSL:

```bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -showcerts \
  -verify_return_error \
  -CAfile internal-root-ca.pem
```

`-servername` gửi SNI. `-CAfile` chỉ định CA dùng để xác minh. Kết quả OpenSSL hữu ích để so sánh với JVM, nhưng không chứng minh truststore của Java đã được cấu hình giống hệt.

Trong môi trường thử nghiệm có thể bật Java SSL debug:

```bash
-Djavax.net.debug=ssl:handshake:verbose
```

Chỉ bật tạm thời để chẩn đoán. Log TLS có thể rất lớn và chứa metadata nhạy cảm; không để mức debug này chạy thường trực trong production.

### 13.4. Lỗi proxy

Kiểm tra đường đi qua proxy:

```bash
curl -v \
  --proxy http://proxy.internal.example:8080 \
  https://api.example.com/health
```

Phân biệt:

- Không kết nối được proxy: DNS/connect/firewall của proxy.
- Proxy trả 407: proxy credentials hoặc policy.
- CONNECT thất bại: proxy không cho phép tunnel tới host/port.
- TLS lỗi sau CONNECT: trust chain/hostname/SNI hoặc TLS inspection CA.
- Origin trả 401/403: credential hoặc authorization tại API đích.

### 13.5. Lỗi pool và response timeout

- `PoolAcquireTimeoutException`: không lấy được connection trong thời gian chờ; kiểm tra max connections, request concurrency và thời gian giữ connection.
- `ReadTimeoutException`/response timeout: response không có dữ liệu trong khoảng thời gian cho phép; kiểm tra upstream latency, proxy và network.
- Connection bị đóng khi tái sử dụng: xem idle timeout của server/load balancer và điều chỉnh `maxIdleTime`.
- DNS đã đổi nhưng vẫn đi tới IP cũ: kiểm tra connection pool và tuổi thọ connection, không chỉ DNS cache.

## 14. Phân loại exception và log an toàn

Một outbound client nên phân biệt lỗi transport, TLS, proxy, timeout và HTTP response. `WebClientRequestException` thường bọc lỗi khi request không hoàn tất được ở tầng connector. Nếu server đã trả HTTP response, WebClient có thể cung cấp status và body qua response APIs hoặc `WebClientResponseException` khi dùng `retrieve()` mặc định.

Ví dụ phân loại theo cause:

```java
return webClient.get()
        .uri("/health")
        .retrieve()
        .bodyToMono(String.class)
        .doOnError(error -> {
            log.warn(
                    "Outbound call failed: type={}, message={}",
                    error.getClass().getSimpleName(),
                    error.getMessage());
        });
```

Đây chỉ là log tổng quát. Production nên bổ sung service name, route template, trace/correlation ID và loại lỗi, nhưng không log:

- Private key, keystore password hoặc truststore password.
- `Authorization`, `Proxy-Authorization`, cookies hoặc API tokens.
- Toàn bộ certificate private material.
- URL có query parameter chứa secret.
- Raw request/response body nếu có dữ liệu cá nhân.

Metrics Reactor Netty có thể cung cấp thông tin về connection time, TLS handshake time, DNS resolver duration, response time, số connection active/idle/pending và số lỗi. Hãy bật observability theo cấu hình ứng dụng để xác định latency nằm ở resolver, connect, TLS hay response.

## 15. Dự án Java 17+ chạy được: WebClient với CA riêng và hostname verification

Dự án mẫu sử dụng:

- Java 17.
- Spring Boot 3.3.5.
- Spring WebFlux/Reactor Netty do Spring Boot quản lý version.
- JUnit 5 và Reactor Test.
- OkHttp MockWebServer và `okhttp-tls` để tạo HTTPS server cục bộ có certificate SAN `localhost`.

Dự án kiểm tra hai hành vi:

1. Client tin certificate CA được truyền vào, kết nối HTTPS tới `localhost` và nhận response.
2. Client tin cùng certificate nhưng gọi bằng hostname `127.0.0.1`, trong khi certificate chỉ có SAN `localhost`; hostname verification phải từ chối kết nối.

Certificate test được tạo tạm trong bộ nhớ, không cần lưu private key test vào repository.

### 15.1. Cấu trúc

```text
webclient-tls-dns/
├── pom.xml
└── src/
    ├── main/java/edu/demo/tls/
    │   ├── TlsWebClientFactory.java
    │   └── CatalogClient.java
    └── test/java/edu/demo/tls/
        └── TlsWebClientTests.java
```

### 15.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webclient-tls-dns</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <okhttp.version>4.12.0</okhttp.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>${okhttp.version}</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>okhttp-tls</artifactId>
            <version>${okhttp.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 15.3. `TlsWebClientFactory.java`

```java
package edu.demo.tls;

import java.security.cert.X509Certificate;
import java.time.Duration;

import io.netty.channel.ChannelOption;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

public final class TlsWebClientFactory {

    private TlsWebClientFactory() {
    }

    public static WebClient create(
            String baseUrl,
            X509Certificate trustedCertificate) throws Exception {

        SslContext sslContext = SslContextBuilder.forClient()
                .trustManager(trustedCertificate)
                .build();

        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
                .responseTimeout(Duration.ofSeconds(5))
                .resolver(spec ->
                        spec.queryTimeout(Duration.ofSeconds(2)))
                .secure(ssl -> ssl
                        .sslContext(sslContext)
                        .handshakeTimeout(Duration.ofSeconds(10)));

        return WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

Factory nhận certificate được tin cậy để dựng trust manager cho test. Trong production, truyền CA certificate đã được tổ chức xác minh hoặc nạp truststore PKCS12 như phần trước.

Việc dùng overload `secure(Consumer<SslContextSpec>)` giữ hostname verification mặc định của Reactor Netty 1.1.

### 15.4. `CatalogClient.java`

```java
package edu.demo.tls;

import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<String> health() {
        return webClient.get()
                .uri("/health")
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

Client chỉ định nghĩa HTTP use case. TLS, trust và network timeout đã được đặt ở connector bên dưới.

### 15.5. `TlsWebClientTests.java`

```java
package edu.demo.tls;

import java.io.IOException;
import java.net.InetAddress;
import java.util.concurrent.TimeUnit;

import javax.net.ssl.SSLHandshakeException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.tls.HandshakeCertificates;
import okhttp3.tls.HeldCertificate;
import okhttp3.HttpUrl;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.web.reactive.function.client.WebClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TlsWebClientTests {

    private MockWebServer server;
    private HeldCertificate serverCertificate;
    private CatalogClient catalogClient;

    @BeforeEach
    void setUp() throws Exception {
        serverCertificate = new HeldCertificate.Builder()
                .commonName("localhost")
                .addSubjectAlternativeName("localhost")
                .build();

        HandshakeCertificates serverCertificates =
                new HandshakeCertificates.Builder()
                        .heldCertificate(serverCertificate)
                        .build();

        server = new MockWebServer();
        server.useHttps(serverCertificates.sslSocketFactory(), false);
        server.start(InetAddress.getByName("127.0.0.1"), 0);

        WebClient webClient = TlsWebClientFactory.create(
                server.url("/").toString(),
                serverCertificate.certificate());

        catalogClient = new CatalogClient(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void trustedCertificateAndMatchingHostnameSucceed()
            throws Exception {

        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "text/plain")
                .setBody("healthy"));

        StepVerifier.create(catalogClient.health())
                .expectNext("healthy")
                .verifyComplete();

        var request = server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/health", request.getPath());
    }

    @Test
    void trustedCertificateDoesNotAllowWrongHostname()
            throws Exception {

        HttpUrl wrongHostUrl = server.url("/")
                .newBuilder()
                .host("127.0.0.1")
                .build();

        WebClient wrongHostClient = TlsWebClientFactory.create(
                wrongHostUrl.toString(),
                serverCertificate.certificate());

        CatalogClient wrongHostCatalog =
                new CatalogClient(wrongHostClient);

        StepVerifier.create(wrongHostCatalog.health())
                .expectErrorSatisfies(error ->
                        assertTrue(
                                hasCause(error, SSLHandshakeException.class),
                                error.toString()))
                .verify();
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expected) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (expected.isInstance(current)) {
                return true;
            }
        }

        return false;
    }
}
```

Test thứ hai dùng certificate được trust nhưng hostname trong URL không khớp SAN. Nó chứng minh trust chain và hostname verification là hai bước độc lập.

### 15.6. Chạy test

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Bộ test có hai trường hợp:

1. HTTPS thành công khi CA được tin cậy và hostname khớp SAN.
2. TLS handshake thất bại khi hostname không khớp SAN, dù certificate đã được trust.

Kết quả mong đợi sau khi Maven chạy thành công:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Đây là kết quả kỳ vọng để đối chiếu khi thực thi; tài liệu không khẳng định Maven đã được chạy trong môi trường biên soạn.

## 16. Lỗi cấu hình thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Truststore thiếu CA nội bộ | `PKIX path building failed` | Import đúng CA/intermediate đã xác minh |
| Server không gửi intermediate | Client không dựng được chain | Sửa server certificate chain |
| Certificate hết hạn | TLS handshake thất bại | Gia hạn và triển khai certificate mới |
| SAN không khớp hostname | Hostname verification thất bại | Dùng hostname đúng hoặc cấp certificate có SAN phù hợp |
| Dùng IP thay hostname | SNI/SAN có thể không khớp | Giữ hostname dịch vụ trong URI |
| Dùng trust-all manager | Mất xác minh server identity | Cấu hình truststore hợp lệ |
| Dựng `SslProvider` nhưng quên hostname configurator | Có thể bỏ qua hostname verification | Gắn `HOSTNAME_VERIFICATION_CONFIGURER` |
| mTLS thiếu private key hoặc chain | Server từ chối client certificate | Kiểm tra PKCS12/PEM và key pair |
| Dùng origin `Authorization` để xác thực proxy | Proxy vẫn trả 407 | Cấu hình proxy credentials riêng |
| Proxy không cho CONNECT | HTTPS tunnel không được tạo | Kiểm tra proxy policy và CONNECT support |
| Trust CA của TLS inspection không đúng | Handshake thất bại qua proxy | Xác minh CA proxy và trust policy |
| DNS laptop đúng nhưng container sai | `UnknownHostException` | Kiểm tra DNS từ runtime thực tế |
| DNS TTL ngắn nhưng vẫn dùng IP cũ | Connection pool giữ TCP connection cũ | Điều chỉnh connection max lifetime/idle policy |
| Response timeout quá ngắn | Request streaming chậm bị ngắt | Dùng read interval phù hợp với contract |
| Chỉ đặt timeout tổng | Khó xác định giai đoạn chậm | Đặt DNS/connect/handshake/pool/response timeout riêng |
| Tạo connection pool không giới hạn | Tăng socket và tài nguyên khi tải cao | Giới hạn max connections và pending acquire |
| Log toàn bộ TLS/proxy headers | Lộ credential hoặc metadata nhạy cảm | Mask secret và chỉ log metadata cần thiết |

## 17. Checklist production

### TLS và certificate

- URL dùng hostname đúng với SAN của server certificate.
- Server gửi đủ certificate chain.
- Truststore chứa CA được phê duyệt.
- Certificate còn hạn và có usage phù hợp.
- Hostname verification được bật.
- SNI gửi đúng hostname đích.
- mTLS keystore có private key và certificate chain đúng nếu server yêu cầu.
- Private key/password được quản lý qua secret manager.
- Có quy trình rotate certificate/truststore và restart/rebuild client phù hợp.
- Không dùng trust-all hoặc tắt hostname verification.

### Proxy

- Proxy host/port đúng với môi trường runtime.
- `nonProxyHosts` chỉ bypass đúng các host cần truy cập trực tiếp.
- CONNECT được proxy cho phép khi gọi HTTPS.
- Proxy authentication tách biệt với origin authentication.
- Proxy password được quản lý như secret.
- Nếu có TLS inspection, CA của proxy đã được xác minh và cấu hình theo chính sách.
- Xác định rõ DNS hostname đích được resolve ở client hay proxy.

### DNS và connection pool

- DNS resolver/query timeout phù hợp.
- Kiểm tra DNS từ đúng container/VM/Kubernetes namespace.
- Cache TTL phù hợp với cách dịch vụ thay đổi IP.
- Connection max lifetime phù hợp với load balancer/DNS rotation.
- `maxIdleTime` không vượt idle timeout của peer.
- Max connections và pending acquire có giới hạn.
- Không nhầm DNS TTL với tuổi thọ TCP connection.

### Timeout và quan sát

- Có connect timeout.
- Có TLS handshake timeout.
- Có DNS query timeout.
- Có proxy connect timeout nếu dùng proxy.
- Có response timeout phù hợp.
- Có deadline tổng cho use case.
- Có metrics về DNS, connect, TLS handshake, response và connection pool.
- Log phân biệt DNS, TCP, proxy, TLS, HTTP và decoding errors.
- Không log private key, password, token hoặc raw sensitive headers/body.

## 18. Bài tập tự kiểm tra

**Bài 1.** Truststore và keystore khác nhau thế nào?

**Đáp án:** Truststore chứa CA/trust anchors dùng để xác minh certificate peer. Keystore chứa private key và certificate chain của chính client/server để trình danh tính khi được yêu cầu.

**Bài 2.** Certificate chain hợp lệ nhưng hostname không khớp SAN. HTTPS có nên thành công không?

**Đáp án:** Không. Trust chain validation và hostname verification là hai kiểm tra riêng. Certificate phải được tin cậy và nhận diện đúng hostname trong URL.

**Bài 3.** SNI có thay thế hostname verification không?

**Đáp án:** Không. SNI giúp server chọn certificate phù hợp; hostname verification kiểm tra certificate có nhận diện đúng host hay không.

**Bài 4.** Khi nào cần mTLS?

**Đáp án:** Khi server yêu cầu client trình certificate để xác thực danh tính client ở tầng TLS. Client cần key pair/certificate; server phải tin CA đã cấp client certificate.

**Bài 5.** HTTPS qua HTTP proxy dùng CONNECT để làm gì?

**Đáp án:** CONNECT yêu cầu proxy tạo tunnel TCP tới origin. TLS handshake sau đó diễn ra qua tunnel giữa client và endpoint đích, trừ khi proxy thực hiện TLS inspection.

**Bài 6.** Proxy trả 407 khác origin trả 401 thế nào?

**Đáp án:** 407 là proxy authentication; 401 là authentication ở HTTP service đích. Hai credential và policy không giống nhau.

**Bài 7.** DNS TTL đã hết nhưng request vẫn đi tới IP cũ. Vì sao?

**Đáp án:** Connection pool có thể tái sử dụng TCP connection đã mở tới IP cũ; không cần DNS lookup mới cho connection đó. Cần xem connection max lifetime/idle policy.

**Bài 8.** `responseTimeout` có phải deadline tổng của request không?

**Đáp án:** Không. Nó giới hạn khoảng thời gian giữa các lần đọc response ở tầng mạng. Dùng `Mono.timeout()` hoặc deadline tương đương để giới hạn toàn publisher.

**Bài 9.** Vì sao không nên tắt hostname verification khi certificate bị mismatch?

**Đáp án:** Client sẽ không còn xác minh đúng server identity theo hostname và có thể chấp nhận kết nối tới peer giả mạo. Hãy sửa SAN, URL host, SNI hoặc certificate chain.

**Bài 10.** Dùng HTTP proxy, DNS ở laptop phân giải được nhưng ứng dụng không kết nối được. Cần kiểm tra gì?

**Đáp án:** Kiểm tra proxy reachability/authentication, CONNECT policy và DNS view tại nơi thực sự resolve hostname đích (client runtime hoặc proxy), thay vì chỉ kiểm tra laptop.

## 19. Ghi nhớ

- WebClient dùng `ClientHttpConnector`; Reactor Netty là connector phổ biến khi dùng Spring Boot WebFlux.
- HTTPS gồm TCP connection, TLS handshake, trust chain validation và hostname verification.
- Truststore xác minh server; keystore cung cấp client identity khi dùng mTLS.
- SAN phải khớp hostname trong URI; SNI chỉ giúp server chọn certificate.
- Reactor Netty 1.1 bật hostname verification với `secure()` và `secure(Consumer<SslContextSpec>)`; khi truyền `SslProvider` dựng sẵn, cần cấu hình hostname verification rõ ràng.
- Không dùng trust-all manager hoặc tắt hostname verification để né lỗi.
- HTTP proxy dùng CONNECT để tạo tunnel HTTPS; proxy authentication khác origin authentication.
- Reactor Netty mặc định dùng DNS resolver bất đồng bộ; DNS cache TTL và connection pool lifetime là hai cơ chế độc lập.
- Cấu hình timeout riêng cho pool acquire, DNS, TCP connect, proxy connect, TLS handshake và response.
- Chẩn đoán theo đúng giai đoạn: DNS → TCP → proxy → TLS → HTTP → decode.
- Certificate, proxy credential và private key phải được quản lý như secret; log chỉ metadata an toàn.

Khi WebClient không kết nối được, hãy xác định trước **request đang dừng ở DNS, TCP, proxy, TLS hay HTTP**. Sau đó kiểm tra đúng cấu hình của giai đoạn đó; cách này giúp phân biệt lỗi certificate với lỗi mạng và lỗi xác thực proxy.

## Tài liệu chính thức

- Spring Framework 6.2, **WebClient**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html
- Spring Framework 6.2, **WebClient Configuration and ReactorClientHttpConnector**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html
- Reactor Netty 1.1.21, **HTTP Client – SSL/TLS**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/reference/html/index.html
- Reactor Netty 1.1.21, **Proxy Support**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/reference/html/index.html
- Reactor Netty 1.1.21, **Host Name Resolution**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/reference/html/index.html
- Reactor Netty 1.1.21, **Timeout Configuration**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/reference/html/index.html
- Reactor Netty 1.1.21, **`HttpClient` API**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/api/reactor/netty/http/client/HttpClient.html
- Reactor Netty 1.1.21, **`HttpClientSecurityUtils` API**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/api/reactor/netty/http/client/HttpClientSecurityUtils.html
- Netty, **`SslContextBuilder` API**: https://netty.io/4.1/api/io/netty/handler/ssl/SslContextBuilder.html