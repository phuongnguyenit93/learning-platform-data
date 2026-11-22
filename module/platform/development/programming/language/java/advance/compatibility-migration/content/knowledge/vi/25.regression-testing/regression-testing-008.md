# Kiểm thử TLS, chứng chỉ và tích hợp dịch vụ bên ngoài

Trong **Java Advance Compatibility Migration**, một hệ thống có thể build thành công và vượt unit test trên JDK mới nhưng thất bại khi kết nối HTTPS, cơ sở dữ liệu, message broker hoặc API đối tác. Nguyên nhân không nhất thiết nằm trong mã nghiệp vụ: **TLS protocol**, cipher suites, certificate chain, hostname verification, truststore, mutual TLS hoặc TLS provider có thể thay đổi theo JDK, bản vá bảo mật, dependency và container image.

Bài học thuộc chương **Kiểm thử hồi quy**. Mục tiêu là thiết kế bộ kiểm thử cho phép phát hiện lỗi TLS trước khi triển khai, không làm suy yếu xác minh chứng chỉ để biến test thành công, và có bằng chứng rằng các dịch vụ bên ngoài tiếp tục vận hành đúng trên cả JDK baseline lẫn JDK mục tiêu.

Các ví dụ dùng Java 17 và Java 21 để minh họa. Trong hệ thống thực tế, chính sách protocol, cipher, root CA, disabled algorithms và hành vi provider phải được kiểm tra với **JDK vendor, release, bản vá và runtime image thực sự sử dụng**.

## 1. Vì sao TLS cần một bộ regression test riêng?

Nâng JDK có thể tạo thay đổi quan sát được:

- JDK mới có tập CA gốc khác trong truststore.
- Chính sách **jdk.tls.disabledAlgorithms** hoặc **jdk.certpath.disabledAlgorithms** được cập nhật.
- Endpoint bên ngoài chỉ hỗ trợ TLS hoặc thuật toán chữ ký lỗi thời.
- Server thiếu intermediate certificate nhưng máy developer vẫn kết nối được nhờ truststore/cache riêng.
- Client chuyển từ hostname sang IP khiến **Subject Alternative Name (SAN)** không còn khớp.
- HTTP client mới dùng SSL provider khác.
- Client certificate cho **mutual TLS (mTLS)** không được chọn đúng sau khi thay cấu hình.
- Gateway, proxy hoặc service mesh bắt đầu terminate TLS ở một lớp khác.
- ALPN/SNI behavior thay đổi và gRPC/HTTP2 không còn hoạt động.
- Chứng chỉ đối tác được xoay vòng đồng thời với JDK upgrade.
- Container image mới thiếu CA/truststore/secret mount vốn tồn tại trên image cũ.

Một lỗi TLS có thể làm tăng retry, gây đầy queue, làm circuit breaker mở hoặc khiến business transaction thất bại. Vì vậy **compile pass** và **mocked HTTP 200** không đủ để chứng minh integration readiness.

### 1.1. Các tầng kết nối cần phân biệt

~~~text
Java application
       |
       +--> DNS, proxy, routing, TCP
       |
       +--> TLS handshake
       |       |
       |       +--> Protocol/cipher negotiation
       |       +--> Server certificate chain
       |       +--> Trust anchor / path validation
       |       +--> Hostname verification
       |       +--> Client certificate khi mTLS
       |       +--> ALPN/SNI
       |
       +--> HTTP/JDBC/LDAP/Kafka/gRPC
       |
       +--> Application authentication/authorization
       |
       +--> Business response
~~~

HTTP **401/403** thường là lỗi ở tầng ứng dụng sau khi TLS có thể đã thành công. **PKIX path building failed** thường xuất hiện ngay trong giai đoạn xác minh chứng chỉ.

### 1.2. Các mục tiêu regression

| Mục tiêu | Điều phải chứng minh | Ví dụ |
|---|---|---|
| Confidentiality | Kết nối sử dụng TLS theo chính sách | Không tự fallback plaintext |
| Server identity | Certificate chain và SAN hợp lệ | Đúng DNS của đối tác |
| Client identity | mTLS cung cấp đúng certificate | Đối tác chấp nhận client |
| Protocol | Có phiên bản TLS/cipher được cho phép | TLS 1.2/1.3 theo policy |
| Business integration | Request/response contract không đổi ngoài dự kiến | REST, JDBC, Kafka |
| Security rejection | Certificate không tin cậy bị từ chối | Negative tests |
| Resilience | Timeout/retry không gây duplicate side effects | Idempotency |
| Operations | Có telemetry, expiry và rotation runbook | Alert và rollback |

Tương thích không đồng nghĩa bật lại mọi giao thức cũ. Nếu JDK mới từ chối thuật toán yếu theo security policy, kết quả đó có thể đúng và yêu cầu phối hợp nâng cấp đối tác, không phải lý do vô hiệu hóa xác minh.

## 2. JSSE và TLS provider trong Java

**Java Secure Socket Extension (JSSE)** cung cấp API:

- **SSLContext**: cấu hình TLS và key/trust managers.
- **SSLSocket/SSLEngine**: thực hiện kết nối TLS.
- **SSLParameters**: thiết lập protocols, cipher suites, endpoint identification.
- **SSLSession**: quan sát protocol/cipher đã đàm phán.
- **TrustManagerFactory**: xây dựng trust managers từ truststore.
- **KeyManagerFactory**: chọn private key/certificate cho identity của client hoặc server.
- **KeyStore**: chứa certificates và có thể chứa private key entries.
- **HttpsURLConnection** hoặc **java.net.http.HttpClient**: HTTP clients sử dụng TLS.

Các thư viện như Apache HttpClient, OkHttp, gRPC/Netty, Kafka hay JDBC driver có thể dùng JSSE hoặc provider/configuration khác. Không giả định thay một system property sẽ ảnh hưởng mọi outbound connection như nhau.

### 2.1. Truststore và keystore

| Thành phần | Dữ liệu điển hình | Vai trò |
|---|---|---|
| Truststore | CA certificates/trust anchors | Xác minh peer |
| Keystore client | Private key và client certificate chain | Trình bày client identity |
| Server leaf certificate | SAN, validity, key usage, issuer | Xác minh server identity |
| Intermediate CA | Certificate trung gian | Xây dựng trust path |
| Root CA | Trust anchor được phê duyệt | Kết thúc đường tin cậy |
| CRL/OCSP | Revocation status | Kiểm soát certificate thu hồi nếu được cấu hình |

Một client không cần client private key cho HTTPS một chiều thông thường. Ngược lại, mTLS yêu cầu client key material và server phải chấp nhận certificate tương ứng.

### 2.2. Endpoint authentication khác authorization

Certificate hợp lệ cho endpoint không tự cấp quyền business. Một request có thể hoàn tất TLS nhưng nhận HTTP 403 do scope/account. Tương tự, mTLS xác thực danh tính certificate nhưng ứng dụng vẫn có thể kiểm tra authorization riêng.

## 3. TLS versions, cipher suites và security policy

Hai đầu kết nối phải tìm được tập giao nhau giữa các protocols/ciphers mà hai bên hỗ trợ **và** được policy cho phép.

- **TLS 1.2** được hỗ trợ rộng rãi.
- **TLS 1.3** có sẵn trong nhiều JDK hiện đại.
- **TLS 1.0/1.1** là giao thức lỗi thời và thường bị vô hiệu hóa.

Một cipher có thể thuộc danh sách **supported** nhưng không nằm trong danh sách **enabled**, hoặc bị security constraints từ chối.

Các security properties quan trọng:

~~~text
jdk.tls.disabledAlgorithms
jdk.certpath.disabledAlgorithms
~~~

Nội dung mặc định phụ thuộc vendor/version/patch. Không nên mở lại thuật toán yếu toàn JVM chỉ để một integration cũ hoạt động. Nếu cần ngoại lệ, phải có security owner, phân tích rủi ro và thời hạn loại bỏ.

### 3.1. Những yếu tố làm handshake thất bại

| Yếu tố | Ví dụ lỗi | Bước kiểm tra |
|---|---|---|
| TLS version | protocol_version | Enabled protocols của client/server |
| Cipher suite | handshake_failure | Cipher overlap và security constraints |
| Certificate signature | Algorithm constrained | Signature algorithm, key size |
| Certificate path | PKIX failure | Truststore, intermediate, issuer |
| Hostname | SAN mismatch | URL, DNS name, IP SAN |
| SNI | Server trả nhầm certificate | Virtual host và hostname |
| ALPN | HTTP/2/gRPC không chạy | Client/server protocol negotiation |
| mTLS identity | bad_certificate | Client keystore, alias, chain |
| Revocation | CertPath validation | CRL/OCSP policy/network |

**handshake_failure** không chứng minh nguyên nhân chắc chắn là cipher. Cần xem exception chain và peer logs.

## 4. Certificate chain và hostname verification

Một client HTTPS thường kiểm tra:

1. Certificate chain do server cung cấp.
2. Chữ ký và các constraints X.509.
3. Đường tin cậy tới trust anchor hợp lệ.
4. Certificate validity và key usages.
5. Hostname/IP trong URL có khớp SAN không.
6. Revocation status nếu policy đã bật cơ chế tương ứng.

~~~text
Leaf: api.partner.example
          |
          v
Intermediate CA
          |
          v
Root CA trong truststore được phê duyệt
~~~

Server thường gửi leaf và intermediate cần thiết; không nhất thiết gửi root. Một server thiếu intermediate có thể được máy A chấp nhận nhưng lỗi trên máy B do truststore/cache khác.

### 4.1. Untrusted CA và SAN mismatch khác nhau

**Untrusted CA:** chain không dẫn tới một trust anchor được chấp nhận.

**SAN mismatch:** chain có thể hợp lệ nhưng certificate không đại diện cho hostname mà client đang kết nối.

Ví dụ gọi **https://10.0.0.8** trong khi certificate chỉ có DNS SAN **api.partner.example** có thể bị từ chối dù IP đó trỏ tới đúng server. Hướng sửa là dùng DNS name đúng hoặc cấp certificate có IP SAN phù hợp, không tắt hostname verification.

### 4.2. Kiểm thử SAN

Cần có các trường hợp:

- DNS hostname đúng.
- DNS alias không được certificate bao phủ.
- Wildcard hostname đúng và không đúng.
- IP literal nếu ứng dụng thực sự gọi bằng IP.
- Redirect sang domain khác.
- Proxy/load balancer trả certificate riêng.
- Server chọn certificate theo SNI.

Không dựa vào Common Name (CN) fallback vì behavior có thể thay đổi theo client/provider.

### 4.3. Validity và clock

Certificate có **notBefore** và **notAfter**. Một container có system clock sai có thể báo certificate chưa hợp lệ hoặc hết hạn. Kiểm tra time synchronization; thay timezone hiển thị log không giải quyết certificate validity.

### 4.4. Key usage, EKU và CA constraints

Ngoài ngày hết hạn, cần xét:

- Server Authentication/Client Authentication EKU.
- Key Usage.
- Basic Constraints.
- Signature algorithm và key size.
- Intermediate CA chain.
- Name Constraints hoặc policy constraints nếu có.

Một certificate ký đúng không tự động phù hợp cho mọi mục đích TLS.

## 5. Truststore mặc định và truststore riêng

Nhiều JDK có CA truststore trong runtime image, thường ở đường dẫn dạng:

~~~text
$JAVA_HOME/lib/security/cacerts
~~~

Danh sách CA, đường dẫn và provider có thể khác giữa JDK vendors và container images.

Dùng keytool để khảo sát:

~~~bash
keytool -list -cacerts
~~~

Truststore riêng:

~~~bash
keytool -list -v \
  -keystore /secure/config/partner-truststore.p12 \
  -storetype PKCS12
~~~

Tool có thể yêu cầu mật khẩu. Không đưa production passwords vào command line hoặc log công khai.

### 5.1. Import CA kiểm thử vào truststore riêng

~~~bash
keytool -importcert \
  -alias local-test-ca \
  -file test-ca.pem \
  -keystore test-truststore.p12 \
  -storetype PKCS12
~~~

Chỉ import CA test đã được xác minh. Đừng lấy certificate từ một kết nối bị lỗi rồi tin cậy nó mà không xác thực fingerprint/nguồn gốc qua kênh độc lập.

### 5.2. Cấu hình default JSSE truststore

Một số clients sử dụng default SSLContext có thể đọc:

~~~text
-Djavax.net.ssl.trustStore=/secure/config/partner-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Mật khẩu cần được quản lý qua secret manager hoặc cơ chế phù hợp. Không phải mọi thư viện client đều sử dụng default truststore. Một custom SSLContext hoặc một client Netty/Kafka có cấu hình riêng có thể bỏ qua thuộc tính này.

### 5.3. Tránh mở trust quá rộng

Nếu thay truststore mặc định của toàn JVM bằng một file chỉ chứa private CA, những HTTPS integrations khác có thể mất trust public CA. Ngược lại, copy toàn bộ cacerts của máy developer vào container có thể thêm trust anchors ngoài security policy.

Ưu tiên truststore theo client/partner hoặc trust bundle được tổ chức quản lý rõ ràng.

## 6. Tạo SSLContext cho Java HttpClient

Ví dụ Java 17+ chỉ định truststore cho client HTTPS:

~~~java
package example.tls;

import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.Duration;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class PartnerClient {
    public static SSLContext contextFromTruststore(
            Path path, char[] password) throws Exception {

        KeyStore trust = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            trust.load(in, password);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    public static String get(URI endpoint, SSLContext context)
            throws Exception {

        HttpClient client = HttpClient.newBuilder()
            .sslContext(context)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

        HttpRequest request = HttpRequest.newBuilder(endpoint)
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString()
        );

        response.sslSession().ifPresent(session -> {
            System.out.println("TLS: " + session.getProtocol());
            System.out.println("Cipher: " + session.getCipherSuite());
        });

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "Unexpected HTTP status: " + response.statusCode()
            );
        }
        return response.body();
    }
}
~~~

Đoạn code minh họa truststore riêng, không tắt certificate path/hostname verification. Các thông tin endpoint, path và passwords cần được quản lý an toàn.

### 6.1. Lợi ích của SSLContext theo client

- Truststore của partner A không ảnh hưởng partner B.
- Test có thể dùng một CA riêng.
- Không cần thay JVM-wide trust config.
- Dễ ghi rõ policy của mỗi integration.
- Có thể thiết kế certificate rotation theo scope.

Trong production, tái sử dụng HttpClient/connection pool theo lifecycle hợp lý; không nhất thiết tạo client mới cho mỗi request.

### 6.2. Không sử dụng trust-all

Custom trust manager luôn chấp nhận mọi certificate, hoặc hostname verifier luôn true, sẽ vô hiệu hóa một phần quan trọng của TLS authentication. Nếu một regression test chỉ pass nhờ bypass, test đó không chứng minh tính an toàn của endpoint.

### 6.3. Không hardcode TLS 1.2 vô cớ

**SSLContext.getInstance("TLS")** cho provider chọn các protocol được bật theo cấu hình. Nếu sản phẩm có protocol policy riêng, kiểm tra/cấu hình ở client thích hợp. Không cố định chỉ TLS 1.2 khi muốn hỗ trợ TLS 1.3 nếu không có yêu cầu cụ thể.

## 7. Mutual TLS và client certificate

Trong **mTLS**, server và client xác thực certificate của nhau.

~~~text
Java client                       Partner server
    |                                   |
    |-- ClientHello ------------------->|
    |<-- Server certificate ------------|
    |-- Verify CA + hostname -----------|
    |<-- CertificateRequest ------------|
    |-- Client certificate + proof ---->|
    |<-- Verify client certificate -----|
    |======== TLS established =========|
    |-- Business request -------------->|
~~~

Client cần:

- Truststore để xác minh server.
- Keystore với private key/client certificate.
- Certificate có validity, EKU và chain phù hợp.
- Đúng alias nếu có nhiều key entries.
- Server trust được client CA.
- Cơ chế rotation/reload để chuyển cert không downtime ngoài kế hoạch.

### 7.1. SSLContext mTLS

~~~java
package example.tls;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class MutualTlsContexts {
    private static KeyStore load(Path path, char[] password)
            throws Exception {

        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            store.load(in, password);
        }
        return store;
    }

    public static SSLContext create(
            Path clientStorePath, char[] clientPassword,
            Path trustPath, char[] trustPassword) throws Exception {

        KeyStore identity = load(clientStorePath, clientPassword);
        KeyStore trust = load(trustPath, trustPassword);

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm()
        );
        kmf.init(identity, clientPassword);

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
            kmf.getKeyManagers(), tmf.getTrustManagers(),
            new SecureRandom()
        );
        return context;
    }
}
~~~

Đây là ví dụ sử dụng cùng password cho keystore và private key entry. Hệ thống thật có thể cần hai passwords riêng và secret provider phù hợp.

### 7.2. Lỗi mTLS thường gặp

- Không gửi client certificate.
- Keystore không có private key entry.
- Sai alias hoặc password.
- Certificate hết hạn.
- Client certificate không có usage phù hợp.
- Server không trust CA mới.
- Chain thiếu intermediate.
- Key/signature algorithm không được provider hỗ trợ.
- SSLContext/connection pool cũ chưa reload cert mới.
- mTLS thành công nhưng application authorization từ chối.

### 7.3. Test certificate rotation

~~~text
T0: Client dùng cert A, server trust A
T1: Server thêm trust cho cert/CA B
T2: Client chuyển sang B
T3: New TLS connections dùng cert B
T4: Xác nhận mọi instance đã chuyển
T5: Server bỏ trust cert/CA A
~~~

Test phải quan sát connection mới và certificate identity sau khi rotate. Cập nhật secret file không tự đảm bảo client đã tải lại key material.

## 8. HTTPS và các giao thức tích hợp khác

### 8.1. HTTPS/REST

Test:

- Endpoint DNS/port/SNI.
- Truststore/hostname verification.
- Protocol/cipher.
- Proxy, HTTP/2 và ALPN nếu dùng.
- HTTP request/response schema.
- OAuth/token scope sau TLS.
- Timeouts, redirects, retries.
- mTLS khi cần.
- Certificate rotation và pooling.

### 8.2. JDBC

JDBC driver thường có SSL settings riêng. Với PostgreSQL JDBC, **sslmode=verify-full** là chế độ nhằm xác minh chain và hostname theo tài liệu driver. Một chế độ chỉ bật encryption không tự động bảo đảm server identity.

Kiểm tra JDBC driver version và thiết lập TLS thực tế. Thử connection pool, failover database host, server certificate rotation và mTLS nếu có.

### 8.3. Kafka/message brokers

Ví dụ cấu hình Kafka SSL:

~~~properties
security.protocol=SSL
ssl.truststore.location=/secure/kafka/truststore.p12
ssl.truststore.type=PKCS12
ssl.keystore.location=/secure/kafka/client.p12
ssl.keystore.type=PKCS12
~~~

Đây không phải cấu hình production hoàn chỉnh; credentials/keystore passwords phải được quản lý riêng. Với **SASL_SSL**, cơ chế authentication/config khác.

Test cả bootstrap host và broker hostnames được quảng bá; certificate SAN phải phù hợp với các host client thực sự kết nối. Kiểm tra reconnect, consumer rebalance và certificate rotation.

### 8.4. LDAP/LDAPS

Với LDAPS/StartTLS, test trust chain, SAN, domain controllers, referrals và bind authentication. Đừng fallback sang plaintext nếu security policy yêu cầu TLS.

### 8.5. gRPC và HTTP/2

gRPC có thể dựa trên **ALPN** để negotiate HTTP/2. Netty có thể dùng JDK hoặc native TLS provider. Một REST GET thành công không chứng minh gRPC channel hoạt động.

Test chính gRPC client library, SSL provider, ALPN, SNI, certificate identity và application-level status.

### 8.6. SMTP/STARTTLS

Khi dùng STARTTLS, xác nhận client bắt buộc nâng cấp TLS nếu policy yêu cầu. Không cho phép kết nối tự chuyển sang plaintext một cách im lặng.

### 8.7. Proxy và service mesh

~~~text
Java --TLS--> Partner directly

Java --CONNECT tunnel--> Proxy --TLS--> Partner

Java --TLS--> Gateway --TLS--> Partner
~~~

Mỗi kiến trúc có trust boundary riêng. Ở mô hình gateway terminate TLS, Java xác minh certificate gateway, còn gateway chịu trách nhiệm với hop tiếp theo. Không dùng kết quả Java→gateway để khẳng định gateway→partner đã được kiểm chứng.

## 9. Ma trận TLS regression trên JDK cũ và mới

| Trường hợp | JDK baseline | JDK target | Kỳ vọng |
|---|---|---|---|
| Trusted CA + đúng SAN | Test | Test | Thành công |
| Untrusted CA | Test | Test | Bị từ chối |
| Hostname mismatch | Test | Test | Bị từ chối |
| Expired certificate | Test | Test | Bị từ chối |
| Not-yet-valid certificate | Test | Test | Bị từ chối |
| Missing intermediate | Test | Test | Theo chain/trust fixture |
| Client mTLS hợp lệ | Test | Test | Server chấp nhận |
| Thiếu client cert | Test | Test | Server từ chối khi mTLS bắt buộc |
| Client cert sai CA/EKU | Test | Test | Server từ chối |
| TLS 1.2 | Theo policy | Theo policy | Kết nối khi được phép |
| TLS 1.3 | Theo policy | Theo policy | Kết nối khi được phép |
| Protocol/cipher yếu | Test | Test | Không tự mở policy |
| Certificate rotation | Test | Test | Chuyển đổi theo kế hoạch |
| Proxy/SNI/ALPN | Nếu dùng | Nếu dùng | Đúng route/protocol |
| Partner business contract | Test | Test | Kết quả nghiệp vụ chính xác |
| Timeout/retry | Test | Test | Có giới hạn và idempotency |

Nếu security policy mới chủ động từ chối một legacy endpoint, test không nên bị sửa expected result thành success bằng mọi giá. Nó phải ghi rõ đây là blocker cần partner/security xử lý.

## 10. Test bằng local TLS server và CA riêng

Negative tests nên dùng server do đội kiểm thử kiểm soát thay vì gửi request đối kháng tới production partner.

~~~text
Java test runner 17/21
          |
          +--> Valid TLS server
          +--> Untrusted CA server
          +--> Wrong SAN server
          +--> Expired cert server
          +--> mTLS-required server
          +--> Protocol policy test server
          |
          v
JUnit/integration assertions
~~~

Có thể dùng embedded Jetty/WireMock hoặc Testcontainers với certificates do test CA ký.

Fixture gồm:

- Test CA và private key được quản lý riêng.
- Server certificate có SAN hợp lệ.
- Certificate do CA khác ký.
- Certificate với SAN sai.
- Expired/not-yet-valid certificate.
- Client certificate hợp lệ và không hợp lệ.
- Các cấu hình protocol/cipher theo security policy.

Không đưa production private key vào test repository. Nếu dùng test fixture keys trong source control, cần bảo đảm chúng chỉ dùng cho môi trường thử nghiệm và không tạo niềm tin production.

### 10.1. Test fail closed

Với server certificate do CA không được client trust ký, client phải từ chối. Nếu test vẫn nhận business response, cần điều tra xem truststore có được mở rộng sai hoặc xác minh đã bị vô hiệu hóa không.

### 10.2. Không sửa global SSLContext tùy tiện trong test

Một test thay JVM-wide truststore/default SSLContext có thể ảnh hưởng các tests khác, gây flakiness. Dùng SSLContext riêng hoặc JVM process riêng nếu phải thử global properties.

### 10.3. Test phải xử lý certificate validity có kiểm soát

Đừng để certificate test tình cờ hết hạn sau một năm và khiến toàn bộ CI thất bại không có thông tin. Quản lý fixtures, validity window và quy trình gia hạn; với negative expiry tests, tạo hoặc lưu fixture có chủ đích.

## 11. Ví dụ JUnit 5 xác minh phiên TLS

Giả sử test server được tạo và CI cung cấp endpoint/truststore:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Set;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSession;
import org.junit.jupiter.api.Test;

final class PartnerTlsIT {
    @Test
    void validCertificateAndApprovedTlsMustWork()
            throws Exception {

        String url = System.getProperty("tls.test.endpoint");
        String store = System.getProperty("tls.test.truststore");
        String secret = System.getenv("TLS_TEST_STORE_PASSWORD");

        assertNotNull(url);
        assertNotNull(store);
        assertNotNull(secret);

        SSLContext context = PartnerClient.contextFromTruststore(
            Path.of(store), secret.toCharArray()
        );

        HttpClient client = HttpClient.newBuilder()
            .sslContext(context)
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        HttpResponse<String> response = client.send(
            HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build(),
            HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, response.statusCode());

        SSLSession session = response.sslSession()
            .orElseThrow(() ->
                new AssertionError("Expected TLS session"));

        assertTrue(Set.of("TLSv1.2", "TLSv1.3")
            .contains(session.getProtocol()));
        assertNotNull(session.getCipherSuite());
    }
}
~~~

Các protocol chấp nhận trong ví dụ chỉ là policy minh họa. Nếu endpoint bắt buộc TLS 1.3, hãy assert theo contract đó. **PartnerClient** ở phần trước phải nằm trong test classpath.

### 11.1. Negative tests

Đối với untrusted CA, wrong SAN hoặc expired certificate, test kỳ vọng TLS validation thất bại. **SSLHandshakeException** có thể xuất hiện nhưng các tầng transport/async khác có thể wrap exception.

Không assert nguyên văn message của JSSE trừ khi ứng dụng chủ động công bố message ổn định. Cần kiểm tra loại lỗi/cause phù hợp và xác nhận **không có HTTP business response** từ connection không tin cậy.

## 12. Chẩn đoán bằng OpenSSL và keytool

### 12.1. Xem certificate chain với OpenSSL

~~~bash
openssl s_client \
  -connect api.partner.example:443 \
  -servername api.partner.example \
  -showcerts \
  -verify_return_error
~~~

**-servername** gửi SNI để server chọn đúng virtual host. Lệnh có thể cho biết certificate chain, negotiated protocol/cipher và verification diagnostics.

**OpenSSL không mặc định dùng Java truststore của ứng dụng.** OpenSSL thành công trong khi JSSE báo PKIX error vẫn có thể là kết quả đúng của hai trust configurations khác nhau.

### 12.2. Khảo sát TLS version

~~~bash
openssl s_client \
  -tls1_2 \
  -connect api.partner.example:443 \
  -servername api.partner.example
~~~

~~~bash
openssl s_client \
  -tls1_3 \
  -connect api.partner.example:443 \
  -servername api.partner.example
~~~

Kết quả phụ thuộc OpenSSL build và local security configuration, không thay thế test với Java runtime mục tiêu.

### 12.3. Xem certificate metadata

~~~bash
openssl x509 -in server.pem -noout -text
~~~

Kiểm tra issuer, SAN, notBefore/notAfter, key usage, EKU, signature algorithm và key size.

### 12.4. keytool in certificate server

~~~bash
keytool -printcert \
  -sslserver api.partner.example:443 \
  -rfc
~~~

Việc in được certificate không tự động chứng minh client với custom SSLContext sẽ trust certificate đó. Cần test handshake thật với đúng provider/path.

## 13. JSSE debug và phân loại lỗi

Một số JVM diagnostic properties:

~~~text
-Djavax.net.debug=ssl,handshake
-Djava.security.debug=certpath
~~~

Dùng có kiểm soát vì log có thể lớn và chứa thông tin nhạy cảm. Không bật debug liên tục trên production nếu không có yêu cầu rõ.

### 13.1. Exception thường gặp

| Triệu chứng | Nguyên nhân có thể | Điều tra |
|---|---|---|
| SSLHandshakeException | Handshake thất bại | Cause chain, peer logs |
| PKIX path building failed | Trust path không hợp lệ | CA/intermediate/truststore |
| CertPathValidatorException | Certificate không qua policy | Validity, constraints, revocation |
| CertificateExpiredException | Hết hạn | Validity/clock |
| CertificateNotYetValidException | Chưa hợp lệ | Validity/clock |
| No subject alternative names | SAN không phù hợp | Hostname/IP |
| bad_certificate | Peer từ chối certificate | mTLS/CA/EKU |
| handshake_failure | Negotiation thất bại | Protocol/cipher/cert/SNI |
| protocol_version | Protocol không được hỗ trợ | Enabled protocols |
| No appropriate protocol | Local security policy từ chối | Disabled algorithms |
| UnrecoverableKeyException | Không mở được key entry | Key password/alias |
| SocketTimeoutException | Timeout | TCP/handshake/response |
| ConnectException | Không kết nối TCP | DNS/port/firewall |

Không phải mọi **SSLHandshakeException** đều do certificate. Nó cũng có thể đến từ protocol/cipher negotiation hoặc peer policy.

### 13.2. Trình tự triage

1. Xác nhận hostname, port, route và proxy.
2. Ghi JDK vendor/version/patch.
3. Ghi HTTP/JDBC/Kafka client và TLS provider.
4. Xác định đúng SSLContext/truststore/keystore.
5. Kiểm tra SAN, issuer, chain và validity.
6. So sánh enabled protocols/ciphers.
7. Xem exception cause chain và peer logs.
8. Chạy lại trên baseline và target runtime image.
9. Sửa đúng nguyên nhân, không vô hiệu hóa bảo mật.
10. Chạy lại positive và negative regressions.

## 14. Certificate revocation, CRL và OCSP

Tùy security policy, client có thể cần kiểm tra certificate đã bị thu hồi bằng CRL hoặc OCSP. **Không giả định mọi JDK/client bật revocation checking mặc định giống nhau.**

Nếu revocation bắt buộc, kiểm thử:

- Có cấu hình CRL/OCSP phù hợp không.
- Revocation responder có truy cập được qua network/proxy không.
- Timeout/cache của revocation service.
- Fail-open/fail-closed khi responder không truy cập được.
- Certificate nào trong chain được kiểm tra.
- Fixture có revoked certificate có bị từ chối không.

Chỉ bật property mà không có positive/negative tests chưa đủ chứng minh chính sách hoạt động.

## 15. Certificate pinning và xoay vòng

Một số client pin certificate fingerprint hoặc public key. Khi partner rotate, certificate mới có thể hợp lệ theo CA nhưng không khớp pin cũ.

Cần:

- Xác định pin đối tượng: leaf certificate, SPKI/public key hoặc CA.
- Cơ chế backup pin theo policy.
- Thời gian chồng lấn tin certificate A/B.
- Cập nhật client trước khi partner đổi cert.
- Kế hoạch rollback nếu pin mới sai.
- Test positive/negative cho cert A và B.

Không bỏ pinning âm thầm để vượt qua migration nếu nó là biện pháp bảo mật có chủ đích.

## 16. Timeout, retry và idempotency

Không phải mọi network error xảy ra trước khi server xử lý request:

~~~text
Client gửi payment request
       |
       v
Server đã ghi giao dịch
       |
       v
Connection bị ngắt trước khi response tới client
       |
       v
Client nhận I/O timeout
~~~

Nếu tự retry mà không có idempotency key, có thể tạo giao dịch trùng.

Hướng xử lý:

- Phân biệt handshake failure trước request với read timeout sau khi gửi.
- Retry giới hạn với backoff/jitter.
- Không retry vô hạn lỗi trust/SAN validation cố định.
- Dùng idempotency key cho thao tác có side effects nếu API hỗ trợ.
- Test circuit-breaker/retry behavior trên controlled endpoints.
- Không tạo giao dịch thật để thử kết nối âm tính.

## 17. Runtime container và network path

Local Java21 có thể pass còn container Java21 fail vì:

- JDK vendor/patch trong image khác.
- CA bundle khác.
- Truststore mount sai path.
- Client sử dụng default context khác.
- DNS/proxy/SNI route khác.
- Certificate gateway khác.
- System clock sai.
- Image thiếu secrets hoặc permissions.
- Network policy chặn CRL/OCSP.
- HTTP library/provider khác theo classpath.

Do đó phải có **production-like runtime image test**, không chỉ chạy unit tests trên CI host.

### 17.1. CI matrix minh họa

~~~text
PR verification
    |
    +--> JDK baseline:
    |      - Unit tests
    |      - Valid TLS fixture
    |      - Invalid CA/SAN/expiry fixtures
    |      - mTLS tests khi cần
    |
    +--> JDK target:
           - Cùng bộ test
           - Cùng TLS policy assertions

Pre-release
    |
    +--> Docker image smoke
    +--> Staging partner connectivity
    +--> Proxy/SNI/ALPN
    +--> Certificate rotation rehearsal
    +--> Business contract tests
~~~

Một staging partner downtime có thể là incident môi trường, nhưng không được xử lý bằng cách bỏ qua certificate validation. Cần phân loại failures và owner rõ ràng.

## 18. Quan sát TLS sau rollout

Theo dõi:

- Handshake failures theo endpoint.
- Certificate expiry của server/client mTLS.
- Connection timeouts.
- Protocol/cipher negotiated (nếu telemetry có).
- Partner API errors.
- Retry và circuit breaker.
- Queue backlog do connectivity fail.
- Success rate và latency nghiệp vụ.
- Metric availability để tránh đánh đồng mất dữ liệu với 0 errors.

Không ghi private keys, password hoặc token vào logs. Certificate fingerprint/alias và expiry có thể phục vụ chẩn đoán theo chính sách nếu không làm lộ thông tin không cần thiết.

## 19. Tình huống: JDK mới từ chối endpoint legacy

**Triệu chứng:** JDK baseline kết nối được, JDK target gặp handshake failure.

Điều tra:

1. Hai JDK dùng cùng hostname/port/proxy?
2. Security policy/disabledAlgorithms khác nhau?
3. Server có TLS 1.2/1.3 và cipher giao nhau?
4. Chain/signature/key length có phù hợp?
5. Truststore khác nhau?
6. SNI có chọn đúng certificate?
7. Có cần đối tác nâng cấp protocol/certificate?
8. Có security owner phê duyệt ngoại lệ tạm không?

Không mở lại thuật toán lỗi thời cho toàn JVM một cách mặc định.

## 20. Tình huống: container PKIX fail nhưng local pass

Khả năng:

- Container truststore thiếu private CA.
- Local developer từng import CA thủ công.
- Proxy production thay certificate.
- Server gửi chain khác theo region/SNI.
- Secret volume chưa mount hoặc store type sai.
- Runtime image dùng vendor khác.

Cách xử lý: lấy chain trong đúng network path, xác minh truststore Java process đang dùng, kiểm tra SAN và CA qua nguồn độc lập rồi chỉnh cấu hình có kiểm soát. Không copy tùy tiện toàn bộ cacerts từ laptop.

## 21. Tình huống: mTLS fail sau rotation

Khả năng:

- Một số pod vẫn dùng secret cũ.
- SSLContext/connection pool chưa reload.
- Client alias không đúng.
- Cert mới thiếu ClientAuth EKU.
- Server chưa trust CA mới ở mọi backend.
- Chain client thiếu intermediate.
- Rotation overlap window đã đóng quá sớm.

Kiểm tra cert fingerprint/expiry, key entry, alias, secret version, connection refresh và xác nhận từ đối tác. Không trao đổi private key trong chat/email để debug.

## 22. Tình huống: gRPC lỗi dù HTTPS GET thành công

Nếu REST HTTPS trả 200 nhưng gRPC thất bại:

- ALPN có negotiate HTTP/2 không?
- gRPC dùng JDK provider hay native provider?
- Proxy có hỗ trợ HTTP/2 ở đúng hop không?
- SNI và certificate có cùng route không?
- Channel credentials và timeout có đúng không?
- Server trả gRPC status/metadata gì?

Test đúng gRPC client/channel; không dùng kết quả Java HttpClient GET để kết luận.

## 23. Gate phát hành cho TLS regression

### Gate A — Inventory

- Có danh sách TLS integrations/owners.
- Có JDK baseline/target và client versions.
- Có truststore, client certificate và security policy.
- Có certificate expiry và rotation owner.

**GO:** biết các ranh giới cần bảo vệ.

### Gate B — Controlled tests

- Trusted endpoint được chấp nhận.
- Untrusted CA bị từ chối.
- Hostname mismatch bị từ chối.
- Certificate hết hạn bị từ chối.
- mTLS positive/negative tests đạt nếu dùng.
- Protocol/cipher policy được giữ.
- Không có trust-all hoặc disable-hostname-verification.

**GO:** JSSE/client thực sự xác minh peer đúng.

### Gate C — Integration

- Runtime image kết nối staging partner.
- Proxy/SNI/ALPN đúng.
- Business contract đúng.
- Timeout/retry/idempotency được test.
- Certificate rotation path có evidence.
- Monitoring/alerts sẵn sàng.

**GO:** tích hợp hoạt động trong môi trường gần production.

### Gate D — Canary

- JDK target đã chạy canary.
- TLS handshake error rate ổn định.
- SLO/business metrics đạt.
- Có runbook và partner contact.
- Có rollback/forward-fix cho trust bundles/client certs.

**GO:** được phép tăng lưu lượng theo kế hoạch.

### Gate E — Cleanup

- Gỡ workaround tạm.
- Bỏ trust anchors cũ sau overlap window theo policy.
- Cập nhật certificate expiry alerts.
- Lưu kết quả testing và owners.
- Dọn test secrets đúng quy trình.

## 24. Các anti-patterns thường gặp

### 24.1. Chỉ kiểm tra HTTP 200

Không phát hiện trust bypass. **Giải pháp:** thêm negative CA/SAN tests.

### 24.2. Dùng trust-all để sửa PKIX

Làm mất peer authentication. **Giải pháp:** xác minh chain/truststore đúng.

### 24.3. Disable hostname verification để dùng IP

Che lỗi SAN và mở nguy cơ MITM. **Giải pháp:** dùng hostname/certificate phù hợp.

### 24.4. Nhầm OpenSSL trust với Java trust

Hai công cụ có trust/config khác nhau. **Giải pháp:** chạy Java client thật.

### 24.5. Import certificate bất kỳ vào cacerts

Tăng trust ngoài kiểm soát. **Giải pháp:** xác minh fingerprint/nguồn và quản lý CA.

### 24.6. Mở TLS 1.0/1.1 cho toàn JVM

Giảm security posture. **Giải pháp:** partner upgrade hoặc security decision có kiểm soát.

### 24.7. Không diễn tập certificate rotation

Application chạy với cert A nhưng chết khi cert B có hiệu lực. **Giải pháp:** rotation tests và overlap.

### 24.8. Retry vô hạn certificate errors

Lỗi cấu hình không tự hết. **Giải pháp:** phân loại exception, bounded retries.

### 24.9. Nhầm HTTP 403 với TLS failure

Sửa sai lớp. **Giải pháp:** tách handshake và application auth.

### 24.10. Không test production-like container

CA, DNS, mounts, providers khác CI host. **Giải pháp:** smoke trong image thật.

### 24.11. Log passwords/private keys

Rò rỉ secrets. **Giải pháp:** secret manager và log sanitization.

### 24.12. Coi successful handshake là successful integration

Business protocol/schema vẫn có thể sai. **Giải pháp:** test request/response contract sau TLS.

## 25. Checklist kết thúc migration

### JDK và TLS settings

- [ ] Ghi JDK vendor/version/patch của baseline và target.
- [ ] Ghi client library và TLS provider.
- [ ] Xác định truststore/keystore thực sự được sử dụng.
- [ ] Xác định protocol/cipher/algorithm policy.
- [ ] Có test DNS/SNI/ALPN và proxy khi liên quan.
- [ ] Secrets không nằm trong source, logs hoặc lệnh công khai.

### Certificate validation

- [ ] Trusted CA + đúng SAN thành công.
- [ ] Untrusted CA bị từ chối.
- [ ] Hostname mismatch bị từ chối.
- [ ] Expired/not-yet-valid certificates bị từ chối.
- [ ] Key usage/EKU phù hợp.
- [ ] Revocation testing theo policy.
- [ ] Certificate rotation được diễn tập.
- [ ] Không có trust-all/hostname-verifier bypass.

### Integration

- [ ] REST/JDBC/Kafka/LDAPS/gRPC được test khi dùng.
- [ ] Business status/schema/auth đúng sau TLS.
- [ ] Retry/idempotency được kiểm tra.
- [ ] Có staging partner test.
- [ ] Có production-like container smoke.
- [ ] Test cả JDK baseline và target.
- [ ] Negative tests không gây tác động tới partner production.

### Vận hành

- [ ] Có metric/alert handshake failures.
- [ ] Có expiry và rotation owner.
- [ ] Có partner contact và incident runbook.
- [ ] Có rollback policy cho truststore/client certificate.
- [ ] Có evidence theo JDK/image/certificate identity.
- [ ] Security exceptions có người phê duyệt và hạn loại bỏ.

## 26. Mẫu biên bản regression

~~~text
Test ID:
Integration/Partner:
Owner:
Endpoint DNS and port:
Proxy/Network path:
JDK baseline:
JDK target:
JDK vendor/build:
Client library and TLS provider:
Truststore source (no password):
Client cert alias/fingerprint if mTLS:
Allowed protocol/cipher policy:
Negotiated protocol/cipher:
Server certificate issuer/SAN/expiry:
Positive certificate test:
Untrusted CA test:
Hostname mismatch test:
Expired cert test:
mTLS tests:
Rotation test:
Business contract test:
Timeout/retry test:
Exception category:
SLO/Telemetry:
Evidence:
Security approval:
GO/NO-GO:
~~~

Một kết quả ghi PASS mà không có JDK, truststore, certificate identity và endpoint route chỉ là bằng chứng yếu khi cần điều tra sau rotation hoặc cập nhật JDK.

## 27. Tài liệu chính thức để đối chiếu

- **JSSE Reference Guide:** https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html
- **SSLContext API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLContext.html
- **SSLParameters API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html
- **SSLSession API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLSession.html
- **Java HttpClient API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html
- **TrustManagerFactory API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html
- **KeyManagerFactory API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html
- **KeyStore API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html
- **keytool command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html
- **OpenSSL s_client:** https://docs.openssl.org/master/man1/openssl-s_client/
- **PostgreSQL JDBC SSL:** https://jdbc.postgresql.org/documentation/ssl/
- **Kafka security documentation:** https://kafka.apache.org/documentation/#security
- **TLS 1.3, RFC 8446:** https://www.rfc-editor.org/rfc/rfc8446

Các phiên bản JDK và thư viện có thể tiếp tục cập nhật security defaults. Khi áp dụng vào dự án thật, kiểm tra policy và tài liệu theo đúng runtime được triển khai.

---

**Kết luận:** Kiểm thử TLS và chứng chỉ là một phần không thể thiếu của **kiểm thử hồi quy Java migration**. Một ứng dụng build thành công chưa chắc vẫn kết nối được với các hệ thống bên ngoài. Bộ kiểm thử đáng tin cậy phải xác nhận cả positive trust lẫn negative trust, kiểm tra certificate chain/SAN, TLS protocol/cipher, mTLS, certificate rotation và application contract trên hai JDK cùng runtime image gần production. Khi có lỗi, hãy giải quyết đúng trust boundary và phối hợp với đối tác theo chính sách bảo mật, thay vì tắt certificate verification để khiến test xanh.
