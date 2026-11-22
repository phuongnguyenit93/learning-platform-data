# Kiểm thử bảo mật TLS, secret sai và quyền truy cập thiếu

## Bối cảnh và mục tiêu

Trong **Spring Boot Integration**, một ứng dụng có thể gọi HTTP API của đối tác, kết nối PostgreSQL/Redis, phát và tiêu thụ message qua Kafka, RabbitMQ hoặc Pulsar, rồi chuyển dữ liệu giữa các hệ thống qua Spring Integration. Mỗi kết nối đều có một **hợp đồng bảo mật**: xác minh đúng máy chủ, chứng minh danh tính bằng credential hợp lệ, và chỉ được thực hiện các thao tác đã được cấp quyền. Một luồng hoạt động với tài khoản quản trị hoặc cấu hình TLS quá rộng có thể vượt qua happy path nhưng thất bại khi dùng quyền tối thiểu trong production.

Bài học của chương **Hợp đồng và lỗi biên** tập trung vào ba nhóm kiểm thử chủ động tạo điều kiện sai:

1. **TLS/mTLS:** chứng thư không được tin cậy, chứng thư hết hạn, tên máy chủ không khớp, thiếu chứng thư client hoặc truststore/keystore sai.
2. **Secret/credential:** token rỗng, sai, hết hạn, password bị xoay vòng, sai đường dẫn secret hoặc password của keystore không đúng.
3. **Authorization:** danh tính xác thực thành công nhưng thiếu role, scope, ACL hoặc quyền ở đúng tài nguyên và thao tác cần dùng.

Mục tiêu cuối cùng là chứng minh hệ thống **fail closed**: chặn hành vi không được phép, không lộ secret, không tự hạ cấp từ HTTPS xuống HTTP, không retry vô hạn và không ghi nhận nghiệp vụ thành công khi kết nối hoặc quyền truy cập chưa được xác nhận.

> **Phạm vi phiên bản:** Cấu hình minh họa dùng Java 17+, Spring Boot **3.2+** với **SSL bundles** và `RestClient`. Với Spring Boot 3.0/3.1 hoặc các client được thư viện thứ ba tự cấu hình, cách gắn SSL bundle có thể khác. Luôn kiểm tra Boot BOM, loại HTTP client và driver thực tế; không suy ra tất cả adapter của Spring Integration đều dùng chung một TLS context.

## 1. Phân biệt đúng nơi thất bại

Một kết nối có thể bị chặn ở ba ranh giới khác nhau:

```mermaid
flowchart TD
    A[Spring Boot outbound request] --> B{Bắt tay TLS thành công?}
    B -->|Không| C[TLS / chứng thư / hostname / mTLS error]
    B -->|Có| D{Credential hợp lệ?}
    D -->|Không| E[Authentication failure: ví dụ HTTP 401]
    D -->|Có| F{Đủ quyền cho thao tác?}
    F -->|Không| G[Authorization failure: ví dụ HTTP 403]
    F -->|Có| H[Tiếp tục hợp đồng API / nghiệp vụ]
```

HTTP `401` hoặc `403` là **phản hồi tầng HTTP**, chỉ xuất hiện khi client đã đi tới tầng ứng dụng HTTP. Nếu handshake TLS thất bại, không có HTTP response để kiểm tra status; lỗi thường nổi lên qua `SSLHandshakeException`, `SSLPeerUnverifiedException` hoặc exception do client thư viện bọc lại.

| Ranh giới | Ví dụ lỗi | Tín hiệu cần phân biệt | Phản ứng phù hợp |
|---|---|---|---|
| **Trust chain TLS** | Server dùng CA không nằm trong truststore. | `PKIX path building failed`, `SunCertPathBuilderException`, `SSLHandshakeException` hoặc biến thể JSSE. | Dừng kết nối; báo cấu hình trust sai. |
| **Hostname verification** | Client gọi `api.partner.test` nhưng SAN chỉ có `other.partner.test`. | Lỗi hostname/SAN verification khi bắt tay TLS. | Không bỏ qua kiểm tra hostname; sửa endpoint/certificate. |
| **Certificate validity** | Chứng thư hết hạn/chưa có hiệu lực. | Lỗi kiểm tra hạn hoặc trust chain. | Cảnh báo/đổi chứng thư; kiểm tra đồng hồ hệ thống. |
| **mTLS client identity** | Server yêu cầu client certificate nhưng client không gửi, hoặc chứng thư không được server tin. | Handshake bị từ chối; cách báo lỗi phụ thuộc TLS stack và server. | Cấp đúng key/cert và trust chain, không fallback sang anonymous. |
| **Authentication** | Bearer token sai/hết hạn hoặc password DB sai. | HTTP `401`, DB auth error, broker auth failure. | Sửa/rotate credential theo quy trình; không retry liên tục với cùng secret sai. |
| **Authorization** | Token hợp lệ nhưng không có `orders:write`; user DB thiếu `INSERT`. | HTTP `403` (hoặc `404` được thiết kế để ẩn tài nguyên), SQLState/ACL denial. | Yêu cầu đúng quyền tối thiểu; không tự tăng quyền. |
| **Availability** | Broker/DB không chạy, DNS sai, đường mạng bị chặn. | `ConnectException`, timeout, DNS error. | Xử lý như lỗi kết nối theo timeout/retry budget, **không gán nhầm là lỗi TLS hoặc sai mật khẩu**. |

Các ví dụ exception ở bảng chỉ là **dấu hiệu chẩn đoán**, không phải hợp đồng chung cho mọi phiên bản JDK, JDBC driver hay HTTP SDK. Kiểm thử nên xác nhận **nhóm lỗi và hệ quả bảo mật**; chỉ kiểm tra message exception nguyên văn khi thực sự cần và khi thư viện ổn định.

### 1.1. TLS không thay thế authentication/authorization

- **TLS server authentication** xác minh máy chủ mà client đang kết nối tới; mã hóa kênh truyền khi có cấu hình đúng.
- **mTLS** bổ sung chứng thư để máy chủ xác thực **client ở tầng kết nối**. API có thể vẫn yêu cầu token hoặc scope riêng để biết client được phép thao tác gì.
- **Bearer token, API key, username/password** là credential ở tầng ứng dụng hoặc giao thức; chúng có thể đúng ngay cả khi tài khoản chỉ có quyền đọc.
- **ACL, role, scope, database GRANT** quyết định thao tác trên tài nguyên cụ thể. “Đăng nhập thành công” không chứng minh quyền `publish`, `consume`, `INSERT` hoặc `DELETE`.

Thử nghiệm thành công với TLS phải tiếp tục kiểm tra credential và quyền, thay vì coi một lần bắt tay TLS thành công là toàn bộ bài kiểm thử bảo mật.

## 2. Thiết kế hợp đồng kiểm thử âm tính

Mỗi test nên khai báo rõ **điểm gây lỗi, hành vi phải bị từ chối, side effect không được xảy ra và thông tin nào được phép xuất hiện trong log/response**.

| Nhóm | Đầu vào cố ý sai | Điều kiện pass tối thiểu |
|---|---|---|
| TLS-01 | Server certificate do test CA không được trust. | Client không nhận business response; không chuyển sang HTTP; operation không được thực hiện. |
| TLS-02 | Certificate SAN không khớp hostname request. | Handshake bị từ chối kể cả khi issuer CA đã được trust. |
| TLS-03 | Certificate hết hạn hoặc chưa có hiệu lực. | Kết nối bị từ chối; lỗi được phân loại là TLS validation. |
| TLS-04 | Server bắt buộc mTLS, client thiếu client certificate. | Handshake không hoàn tất; không gửi request ở tầng ứng dụng. |
| TLS-05 | Client certificate có nhưng do CA không được server tin hoặc thiếu key tương ứng. | Kết nối bị từ chối; không hạ cấp sang kết nối không xác thực. |
| TLS-06 | Truststore/keystore path hoặc password sai. | Cấu hình/bundle không dùng được; app/adapter báo lỗi rõ, không tự bỏ qua TLS validation. |
| AUTH-01 | Thiếu Bearer token/API key. | Phản hồi auth failure theo hợp đồng; không tạo tài nguyên. |
| AUTH-02 | Token sai/hết hạn hoặc DB/broker password sai. | Không xác thực được; không ghi nhận nghiệp vụ thành công; secret bị che trong log. |
| AUTHZ-01 | Token hợp lệ nhưng thiếu scope `orders:write`. | API từ chối write; read được phép vẫn hoạt động nếu scope cho phép. |
| AUTHZ-02 | DB user có `SELECT` nhưng không có `INSERT`. | Query đọc thành công, lệnh ghi bị từ chối; DB không đổi. |
| AUTHZ-03 | Cache user có quyền `GET` nhưng không có `SET` hoặc key pattern. | Lệnh bị ACL từ chối; client không âm thầm dùng user quản trị. |
| AUTHZ-04 | Broker producer thiếu `produce` hoặc consumer thiếu `consume`/group permission. | Gửi/nhận bị từ chối đúng thao tác; không làm mất message theo chính sách ACK. |
| RECOVERY-01 | Secret được sửa/rotate sau khi test auth failure. | Chỉ hồi phục sau khi client/config được cập nhật đúng cách; không cần nới lỏng TLS hoặc quyền. |

**Không tạo test theo hướng xóa quyền hoặc thay secret trên môi trường production.** Dùng môi trường test cô lập, tài khoản chỉ dành cho test và chứng thư/secret test hết hạn ngắn. Thử nghiệm “thiếu quyền” phải dùng **định danh thực sự thiếu quyền**, không chỉ mock response rồi suy rằng policy ACL của server là đúng.

## 3. Cấu hình TLS đúng cho HTTP client trong Spring Boot

### 3.1. SSL bundle gom truststore, keystore và TLS settings

Spring Boot **3.1+** cung cấp SSL bundles; với `RestClient` từ Boot **3.2+**, có thể áp dụng bundle bằng `RestClientSsl`. `truststore` quyết định CA/certificate nào được client tin; `keystore` và private key dùng khi endpoint yêu cầu **mTLS**. Cả hai có thể nằm trong một bundle, nhưng chỉ cần truststore cho HTTPS server-auth thông thường.

```yaml
# application.yml — ví dụ TLS tới API đối tác
spring:
  ssl:
    bundle:
      jks:
        partner:
          truststore:
            location: ${PARTNER_TRUSTSTORE_LOCATION}
            password: ${PARTNER_TRUSTSTORE_PASSWORD}
            type: PKCS12

integration:
  partner:
    base-url: ${PARTNER_BASE_URL}
    bearer-token: ${PARTNER_API_TOKEN}
```

Các biến môi trường trong ví dụ phải do secret/config management cấp. Với mTLS, bổ sung vào cùng bundle:

```yaml
spring:
  ssl:
    bundle:
      jks:
        partner:
          keystore:
            location: ${PARTNER_KEYSTORE_LOCATION}
            password: ${PARTNER_KEYSTORE_PASSWORD}
            type: PKCS12
          # Có thể cần key.alias / key.password tùy cách đóng gói key.
```

Hai đoạn YAML minh họa **các phần cần ghép vào cùng cấu hình** khi áp dụng mTLS, không phải hai tài liệu cấu hình độc lập có thể dán nối nguyên văn với hai khóa `spring` cạnh nhau. Chứng thư client phải có usage phù hợp và được **server** trust; chỉ đặt file keystore vào client không đủ nếu server không chấp nhận CA hoặc danh tính đó.

Ví dụ tạo `RestClient` theo cấu hình Spring Boot:

```java
import java.net.URI;

import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.web.client.RestClient;

@ConfigurationProperties(prefix = "integration.partner")
record PartnerProperties(URI baseUrl, String bearerToken) {}

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerProperties.class)
class PartnerClientConfiguration {

    @Bean
    RestClient partnerRestClient(
            RestClient.Builder builder,
            RestClientSsl ssl,
            PartnerProperties properties) {

        return builder
                .baseUrl(properties.baseUrl().toString())
                .apply(ssl.fromBundle("partner"))
                .defaultHeader(HttpHeaders.AUTHORIZATION,
                        "Bearer " + properties.bearerToken())
                .build();
    }
}
```

`RestClientSsl` được Spring Boot auto-configuration cung cấp cho RestClient; `RestClient.Builder` cũng cần đến từ context tương ứng. Đây là đoạn minh họa cấu hình trong một ứng dụng đã có `spring-boot-starter-web` hoặc các dependency REST client phù hợp, không phải file Java độc lập hoàn chỉnh. Trong ứng dụng thực tế cần **validate `baseUrl` là HTTPS**, `bearerToken` không rỗng, và đưa cơ chế rotation phù hợp vào thiết kế. Đặc biệt, header mặc định tạo lúc build client có thể giữ token cũ sau khi secret được đổi; đừng giả định Spring tự cập nhật chuỗi token đã đặt vào builder.

### 3.2. Cấu hình TLS nào cần được kiểm tra ngoài truststore?

| Cấu hình | Rủi ro nếu sai | Cách kiểm thử |
|---|---|---|
| **Root/intermediate CA** | `PKIX` fail do thiếu chain hoặc tin nhầm CA. | CA hợp lệ theo test fixture; CA lạ phải bị chặn. |
| **SAN hostname** | Tin đúng CA nhưng kết nối nhầm host. | Cert SAN `wrong.test` dùng cho URL `https://localhost` phải thất bại. |
| **Validity (notBefore/notAfter)** | Cert hết hạn hoặc chưa hiệu lực. | Dùng test cert riêng có kỳ hạn phù hợp; xác nhận đồng hồ test. |
| **SNI** | Server nhiều chứng thư trả chứng thư sai khi hostname/SNI khác nhau. | Kiểm tra endpoint thật với hostname dự kiến; tránh chỉ kết nối bằng IP để kết luận. |
| **TLS versions/ciphers** | Client/server không có bộ thuật toán chung. | Đảm bảo cấu hình cho phép các phiên bản được tổ chức phê duyệt; test kết nối bị từ chối với phiên bản ngoài policy. |
| **mTLS client cert + private key** | Thiếu key, sai alias hoặc client cert không được server tin. | Server `clientAuth=REQUIRE`: client không có cert thất bại, client có cert hợp lệ thành công. |
| **Truststore/keystore secret** | Password sai làm không mở được store; file không đọc được. | Test startup/config error, không nhầm với HTTP `401`. |

**Tuyệt đối không dùng** `trustAll`, `InsecureTrustManagerFactory`, `NoopHostnameVerifier`, `HostnameVerifier` luôn trả `true`, `curl -k` hoặc `spring.ssl` cấu hình bỏ kiểm tra hostname để “sửa” test TLS đang đỏ. Những cách này bỏ đi điều kiện mà test phải xác minh. Không đưa private key, password, bearer token thật hoặc file `.p12` chứa key vào Git; dùng fixture không nhạy cảm chỉ dành cho test và cấp quyền truy cập file chặt chẽ.

### 3.3. Tạo fixture chứng thư cho test cô lập

Có thể dùng `keytool` từ JDK để tạo **chứng thư tự ký chỉ dành cho môi trường test**. Ví dụ sau tạo endpoint test với SAN `localhost` và truststore chứa chính certificate đó:

```bash
# Chạy trong thư mục tạm dành cho test, không commit file có private key.
keytool -genkeypair -alias partner-local -keyalg RSA -keysize 3072 \
  -storetype PKCS12 -keystore partner-server.p12 -storepass test-only-pass \
  -keypass test-only-pass -validity 2 \
  -dname "CN=localhost, OU=IntegrationTests, O=Example, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"

keytool -exportcert -alias partner-local \
  -keystore partner-server.p12 -storepass test-only-pass \
  -rfc -file partner-server.crt

keytool -importcert -noprompt -alias partner-local \
  -file partner-server.crt -storetype PKCS12 \
  -keystore partner-truststore.p12 -storepass test-only-pass
```

Password `test-only-pass` là **giá trị công khai dành riêng cho fixture** trong ví dụ, tuyệt đối không dùng cho môi trường thật. Khi kiểm thử hostname mismatch, tạo một chứng thư **được trust nhưng chỉ có SAN khác** như `other.example.test`, rồi gọi HTTPS URL `localhost`; điều này cô lập lỗi hostname khỏi lỗi trust chain. Khi kiểm thử expiry, cần fixture hết hạn/không có hiệu lực riêng. Không sửa truststore toàn JVM để được phép kết nối mọi server.

## 4. Ví dụ integration test TLS thật, không tắt xác minh

Kiểm thử contract phía client cần có một TLS server thật. Có thể dùng WireMock HTTPS, MockWebServer hoặc một server test khác được cấu hình TLS. Ví dụ JUnit 5 dưới đây dùng **OkHttp MockWebServer + okhttp-tls** để tạo một server với certificate tự ký chỉ tin trong test. Test chứng minh hai điều: **JVM client mặc định từ chối certificate lạ**, và **client có trust riêng được cấu hình tường minh mới kết nối thành công**.

Dependency test (chọn phiên bản tương thích, ví dụ dòng OkHttp 4.x):

```groovy
testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
testImplementation 'com.squareup.okhttp3:okhttp-tls:4.12.0'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
```

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.net.http.HttpClient;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.tls.HandshakeCertificates;
import okhttp3.tls.HeldCertificate;
import org.junit.jupiter.api.Test;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

class TlsContractIT {

    @Test
    void rejectsUnknownCertificateButAcceptsExplicitTestTrust() throws Exception {
        HeldCertificate serverCert = new HeldCertificate.Builder()
                .commonName("localhost")
                .addSubjectAlternativeName("localhost")
                .build();
        HandshakeCertificates serverTls = new HandshakeCertificates.Builder()
                .heldCertificate(serverCert)
                .build();

        try (MockWebServer server = new MockWebServer()) {
            server.useHttps(serverTls.sslSocketFactory(), false);
            server.enqueue(new MockResponse().setResponseCode(200).setBody("ok"));
            server.start();

            String url = server.url("/health").toString();
            assertThrows(ResourceAccessException.class, () ->
                    RestClient.create().get().uri(url).retrieve().body(String.class));

            HandshakeCertificates clientTrust = new HandshakeCertificates.Builder()
                    .addTrustedCertificate(serverCert.certificate())
                    .build();
            SSLContext sslContext = SSLContext.getInstance("TLS");
            sslContext.init(null,
                    new TrustManager[]{clientTrust.trustManager()},
                    new SecureRandom());

            RestClient trustedClient = RestClient.builder()
                    .requestFactory(new JdkClientHttpRequestFactory(
                            HttpClient.newBuilder().sslContext(sslContext).build()))
                    .build();

            assertEquals("ok", trustedClient.get().uri(url)
                    .retrieve().body(String.class));
            assertEquals(1, server.getRequestCount());
        }
    }
}
```

Test trên dùng **truststore test đặt riêng trong `SSLContext`**, không thiết lập chế độ trust all. Với phiên bản framework/client cụ thể, exception được bọc có thể khác; nếu cần kiểm tra chính xác lỗi certificate, duyệt cause chain để tìm `SSLHandshakeException`/certificate validation thay vì cố định toàn bộ message lỗi của JDK. `server.getRequestCount() == 1` chứng minh lần bắt tay không được tin không trở thành một HTTP request hợp lệ tới server, sau đó lần bắt tay được tin mới tới ứng dụng.

**Cần thêm ba ca độc lập** vì test trên mới kiểm tra trust chain:

1. **Hostname mismatch:** cấp certificate được client trust nhưng SAN không chứa hostname request; client vẫn phải từ chối.
2. **mTLS:** cấu hình MockWebServer/server test yêu cầu client certificate và tin CA client test. Client không có key/cert phải bị từ chối; client có key/cert hợp lệ mới thành công.
3. **Expiry/rotation:** dùng cert quá hạn và một cert mới hợp lệ, kiểm tra lỗi và quy trình thay trust/client certificate; không tự động giả định bundle được reload khi file đổi trên disk.

Với API mTLS thực, bước kiểm thử cuối nên chạy qua **đúng endpoint/ingress và server TLS policy** đang được tổ chức sử dụng. Một MockWebServer chỉ chứng minh JSSE/client behavior và mapping config, không chứng minh cấu hình mTLS hoặc ACL của ingress production.

## 5. Kiểm thử secret sai, thiếu và hết hạn

### 5.1. Không phải mọi secret lỗi đều tạo HTTP 401

| Secret | Ví dụ lỗi | Biểu hiện thường gặp | Lưu ý |
|---|---|---|---|
| Bearer token / API key | Sai, thiếu, hết hạn, `aud`/issuer không hợp lệ. | `401` hoặc phản hồi auth failure theo contract. | Một số API chọn status khác, phải xác nhận với tài liệu endpoint. |
| Username/password database | Password sai, secret trỏ nhầm environment. | Lỗi driver/authentication khi mở connection. | DataSource có thể khởi tạo connection khi startup **hoặc lười tạo** ở lần truy vấn đầu. |
| Redis ACL user/password | `WRONGPASS`, `NOAUTH`, tài khoản bị disable. | Redis auth error. | `NOPERM` là lỗi **quyền** sau authentication, không phải sai password. |
| Broker SASL token/username | SASL authentication fail, token hết hạn. | Không lập được session producer/consumer; listener container có thể không chạy. | TLS handshake có thể thành công trước khi broker từ chối credential. |
| TLS keystore/truststore password | Không mở được `.p12`/`.jks`. | Lỗi tạo SSL bundle/SSL context, có thể xảy ra khi start app. | Không có HTTP status vì chưa tạo được kết nối ứng dụng. |
| Client certificate secret/key | Key không khớp certificate hoặc file không đọc được. | SSL context tạo lỗi hoặc mTLS handshake fail. | Không sửa bằng cách tắt client authentication. |

**Ca lỗi do thiếu biến môi trường**: với cấu hình `${PARTNER_API_TOKEN}` không có giá trị, Spring có thể lỗi lúc bind/configure hoặc tạo client, tùy bean được khởi tạo khi nào. Thiết kế nên kiểm tra `null/blank` ngay từ startup bằng `@Validated` + constraint (`@NotBlank`), thay vì gửi chuỗi `Bearer null` hoặc `Bearer ` xuống API rồi mới phát hiện ở runtime.

### 5.2. Phản hồi HTTP 401 và 403 cần được tách biệt

Ví dụ contract API `POST /orders` dùng Bearer token:

```http
POST /orders HTTP/1.1
Host: api.partner.test
Authorization: Bearer <redacted>
Content-Type: application/json

{"orderId":"O-42"}
```

| Test | Token | Permission | Kỳ vọng |
|---|---|---|---|
| Hợp lệ, đủ quyền | Chữ ký/hạn/issuer/audience hợp lệ. | `orders:write` | Server chấp nhận theo contract; side effect xuất hiện đúng một lần. |
| Thiếu token | Không có header. | Không xét. | Thường HTTP `401`; không có order mới. |
| Token sai/hết hạn | Invalid signature hoặc expired. | Không xét. | Thường HTTP `401`; không có order mới; không log nguyên token. |
| Token hợp lệ, scope chỉ đọc | Valid. | Chỉ `orders:read` | Thường HTTP `403`; không có order mới. |
| Token hợp lệ, quyền đúng nhưng resource không thuộc tenant | Valid. | Thiếu quyền trên resource tenant khác. | Bị từ chối, có thể `403` hoặc `404` theo hợp đồng chống lộ tồn tại tài nguyên. |

**Các mã status trên là quy ước phổ biến, không áp đặt cho mọi API.** Một hệ thống có thể dùng `404` để không tiết lộ tài nguyên tồn tại; nếu hợp đồng như vậy thì kiểm thử phải kiểm tra `404` **và không có side effect**. Đừng sửa code bằng cách retry `401/403` không giới hạn, hoặc đổi request sang token quản trị khi gặp lỗi.

### 5.3. Ví dụ kiểm thử mapping 401/403 tại HTTP adapter

Đối với một client sử dụng `RestClient.retrieve()` với default status handling, Spring ném exception khi nhận 4xx. Đoạn trích kiểm thử dưới đây giả sử fixture `MockWebServer` đã bật HTTPS với certificate được client trust từ mục 4, và `client` gọi chính server đó:

```java
server.enqueue(new MockResponse().setResponseCode(401));
assertThrows(HttpClientErrorException.Unauthorized.class,
        () -> client.get().uri("/orders").retrieve().toBodilessEntity());

server.enqueue(new MockResponse().setResponseCode(403));
assertThrows(HttpClientErrorException.Forbidden.class,
        () -> client.post().uri("/orders")
                .body("{\"orderId\":\"O-42\"}")
                .retrieve().toBodilessEntity());
```

Đây là **kiểm thử cách client xử lý status**, chưa chứng minh authentication hoặc phân quyền trên server thật; `MockWebServer` trả status theo kịch bản lập sẵn. Muốn kiểm tra “token hợp lệ nhưng thiếu scope” thật, phải chạy **authorization server/resource server hoặc môi trường API test** với policy RBAC/ABAC đang dùng, sau đó kiểm tra cả HTTP response và dữ liệu phía server.

### 5.4. Rotation: thay secret có đủ để client hồi phục?

Cần kiểm tra ít nhất hai trường hợp:

1. Credential cũ bị thu hồi sau khi credential mới có hiệu lực. Khi request với credential cũ bị từ chối, ứng dụng phải **không chấp nhận thành công giả**, phát cảnh báo và sử dụng credential mới khi được cấp đúng cách.
2. Secret manager cập nhật token/password. Xác nhận **client/pool/cache/connection** đã nạp credential mới bằng restart, refresh hoặc cơ chế hot reload được hỗ trợ thực tế; không giả định `${ENV_VAR}` hay một `@Value` field tự thay đổi trong tiến trình chỉ vì secret ngoài môi trường đổi.

Với bearer token có thể refresh, chỉ nên thiết kế **một nơi sở hữu refresh**; nếu nhiều thread cùng nhận `401`, tránh đồng loạt refresh token và gửi lại hàng nghìn request. Chỉ retry sau khi đã lấy **credential mới hợp lệ** và nằm trong deadline, không gửi lại nguyên secret sai liên tục. Với pool JDBC hoặc broker client, việc rotate password có thể cần tái tạo connection/container theo driver/configuration cụ thể.

## 6. Kiểm thử quyền tối thiểu cho DB, cache và broker

### 6.1. Database: test đúng quyền trên đúng bảng

Một lời gọi `SELECT 1` hoặc `DataSource.getConnection()` thành công **chỉ chứng minh kết nối/authentication cơ bản**, không chứng minh quyền trên bảng nghiệp vụ. Ví dụ trên PostgreSQL trong **test database cô lập**:

```sql
-- Chạy bằng vai trò quản trị của TEST DB, dùng password giả chỉ cho test.
CREATE ROLE integration_reader LOGIN PASSWORD 'local-test-password';
GRANT CONNECT ON DATABASE integration_test TO integration_reader;
GRANT USAGE ON SCHEMA public TO integration_reader;
GRANT SELECT ON TABLE public.orders TO integration_reader;
-- Cố ý KHÔNG cấp INSERT/UPDATE/DELETE cho orders.
```

Tạo datasource thứ hai bằng `integration_reader` rồi xác minh:

```sql
SELECT id, status FROM public.orders LIMIT 1;
-- Thành công nếu dữ liệu/schema/quyền đúng.

INSERT INTO public.orders(id, status) VALUES ('O-SECURITY-TEST', 'NEW');
-- Phải bị từ chối: PostgreSQL thường báo SQLSTATE 42501 (insufficient_privilege).
```

Điều kiện pass: read được phép hoạt động; write bị từ chối; không xuất hiện row `O-SECURITY-TEST`; dịch vụ **không tự chuyển sang một datasource quản trị khác** để thực hiện thay. Phải xác nhận quyền schema và quyền table thực sự thuộc **test role**, tránh test chạy bằng superuser rồi kết luận sai. PostgreSQL `42501` là mã cụ thể cho PostgreSQL; driver của MySQL hoặc database khác có mã khác.

Với ứng dụng JPA/Hibernate, test cần thực thi qua đúng repository/service method (bao gồm flush/commit) vì lỗi có thể chưa nổi lên đến khi flush transaction. Migration schema như Flyway/Liquibase nên dùng principal riêng với quyền DDL cần thiết; không mở thêm DDL cho runtime application chỉ để migration qua test.

### 6.2. Redis: authentication khác ACL

Redis ACL có thể phân quyền theo **lệnh** (`GET`, `SET`, `DEL`) và **key pattern**. Hai kiểm thử khác nhau:

- **Sai password:** Redis từ chối authentication (`WRONGPASS`/`NOAUTH` tùy tình huống và phiên bản), không chạy lệnh ứng dụng.
- **Đăng nhập thành công nhưng ACL chỉ đọc:** `GET cache:products:A1` được phép; `SET cache:products:A1 ...` bị `NOPERM`; lệnh vào key ngoài `cache:products:*` cũng phải bị chặn nếu ACL giới hạn key.

Khi dùng Spring Data Redis, exception có thể bị bọc trong `RedisConnectionFailureException` hoặc `RedisSystemException`/exception chuyên biệt tùy driver và điểm lỗi. Không gắn cứng toàn bộ message exception vào contract test; đo **lệnh có/không được thực thi** và kiểm tra đúng user/ACL ở Redis test instance. Nếu một luồng đọc cache thất bại vì thiếu quyền, cần biết ứng dụng **fail request** hay **bypass cache có kiểm soát** theo hợp đồng; không tự coi mọi lỗi ACL là cache miss rồi silently trả dữ liệu sai.

### 6.3. Kafka, RabbitMQ, Pulsar: quyền đọc và ghi độc lập

| Broker / giao thức | Phân quyền cần kiểm tra | Kịch bản âm tính |
|---|---|---|
| **Kafka** | Principal có quyền trên topic, consumer group và thao tác cần thiết theo ACL; SASL/TLS là tầng xác thực riêng. | Producer thiếu quyền `Write` topic không publish được; consumer thiếu `Read` topic/group bị từ chối. |
| **RabbitMQ** | User có quyền `configure`, `write`, `read` trên resource trong virtual host theo regex permission. | Thiếu quyền publish vào exchange hoặc consume queue gây lỗi channel/permission, không coi kết nối AMQP thành công là đủ. |
| **Pulsar** | Authentication role và quyền `produce`/`consume` trên namespace/topic theo policy. | Producer thiếu `produce` hoặc consumer thiếu `consume` không gửi/nhận được; có thể từ chối lúc tạo producer/consumer. |

Kiểm thử cần dùng **broker thật với auth/ACL bật** hoặc môi trường staging tương đương. Một broker standalone/Testcontainer **không bật authorization** không thể chứng minh role/ACL được áp dụng, dù message gửi/nhận thành công. Với Kafka, lỗi có thể là `TopicAuthorizationException` hoặc lỗi group authorization; với Pulsar/RabbitMQ, loại exception và thời điểm thất bại phụ thuộc client và plugin auth. Kiểm tra cả việc producer/consumer **đã ACK/commit offset** hay chưa: không được xác nhận message là xử lý xong khi side effect phía đích bị chặn do thiếu quyền.

### 6.4. Spring Integration và ranh giới error channel

Ví dụ một `IntegrationFlow` nhận message rồi gọi outbound gateway. TLS/auth failure của outbound adapter cần đi vào **đường xử lý lỗi đã thiết kế**; nếu xử lý bất đồng bộ, error có thể xuất hiện trên `errorChannel`, còn lời gọi đồng bộ có thể ném exception qua caller. Không viết catch-all rồi return kết quả “OK” khi adapter không gửi được message. Phân loại lỗi thành:

```text
TLS certificate / hostname / wrong credentials / missing ACL
  -> Lỗi cấu hình hoặc quyền: fail fast, cảnh báo, cô lập luồng, chờ sửa cấu hình.

Timeout / 429 / 503 có điều kiện
  -> Retry hữu hạn với backoff + jitter + deadline, nếu thao tác an toàn/idempotent.

Payload sai hợp đồng / poison message
  -> Quarantine hoặc dead-letter theo chính sách, không retry vô hạn.
```

Với consumer message, có thể chọn **tạm ngừng consumer và giữ backlog** khi bị lỗi quyền kéo dài trên toàn bộ hệ thống, thay vì gửi mọi message sang DLT chỉ vì cùng một secret bị rotate sai. Sau khi quyền/secret được sửa, khởi động lại hoặc refresh listener theo cách được thư viện hỗ trợ và kiểm tra redelivery/idempotency.

## 7. Chính sách retry, fallback và an toàn dữ liệu khi lỗi bảo mật

| Loại lỗi | Retry? | Fallback? | Cần bảo toàn gì? |
|---|---|---|---|
| Cert không tin, hết hạn, hostname không khớp | **Không retry mù** cùng cấu hình. | Không downgrade HTTP hoặc trust-all. | Chặn side effect; lưu công việc chưa làm trong nguồn bền vững nếu cần. |
| Thiếu client cert mTLS | Không retry đến khi cấu hình được sửa. | Không bỏ mTLS. | Không ACK nghiệp vụ chưa xử lý. |
| Bearer token sai/thiếu | Không gửi lại cùng secret liên tục; có thể refresh có giới hạn nếu hợp đồng hỗ trợ. | Không dùng token admin thay thế. | Đảm bảo không có thao tác trái phép; che secret. |
| HTTP 403/DB permission denied/broker ACL deny | Thông thường **không** retry cho cùng principal và policy chưa đổi. | Không tự cấp thêm quyền hoặc đổi account có quyền rộng. | Giữ task/event an toàn, cảnh báo cấu hình ACL. |
| HTTP 429/503, network timeout | Có điều kiện, giới hạn attempt/deadline/backoff. | Có thể đưa vào queue/outbox. | Idempotency nếu kết quả từ xa chưa chắc chắn. |

**Không ACK message chỉ vì một HTTP request đã được tạo**, nếu request thất bại ở TLS hoặc quyền truy cập. Nếu consumer đã commit offset trước khi task nền xác minh thành công, message có thể bị mất dù người dùng nghĩ hệ thống đã xử lý. Ngược lại, redelivery sau khi DB đã commit có thể tạo side effect trùng; cần **inbox/outbox, idempotency key hoặc transaction phù hợp** theo hợp đồng hệ thống.

Với HTTP API đồng bộ, trả lỗi đã phân loại mà không tiết lộ nội tình như truststore path, full certificate chain, password, token hoặc thông tin tài khoản. Với health/readiness, `UP` của process không chứng minh khả năng gọi downstream hoặc được cấp quyền; xác định probe nào cần kiểm tra endpoint phụ thuộc mà không tạo tải hay thực hiện giao dịch thay đổi dữ liệu.

## 8. Ma trận kiểm thử tích hợp theo lớp và mục tiêu

| Mã | Thiết lập | Thao tác | Kết quả quan sát cần chứng minh |
|---|---|---|---|
| **S01** | HTTPS server cert do CA hợp lệ trong test truststore cấp. | GET endpoint. | TLS đúng, HTTP thành công với credential/scope đủ quyền. |
| **S02** | Server cert tự ký lạ. | GET endpoint. | TLS bị từ chối; không gọi HTTP fallback. |
| **S03** | Cert được trust nhưng SAN sai. | GET hostname thật. | Hostname verification chặn request. |
| **S04** | Server yêu cầu mTLS, client không có certificate. | GET endpoint. | Handshake bị từ chối; không chuyển anonymous. |
| **S05** | Client certificate đúng CA, key hợp lệ. | GET endpoint mTLS. | TLS thành công; quyền ứng dụng vẫn được kiểm tra riêng. |
| **S06** | Truststore/keystore password sai. | Start context hoặc khởi tạo client. | Lỗi cấu hình được phát hiện; không silent disable TLS. |
| **S07** | API không có token hoặc token hết hạn. | POST tạo nghiệp vụ. | Auth failure theo contract; không có row/resource mới. |
| **S08** | API có token hợp lệ nhưng thiếu `orders:write`. | POST tạo nghiệp vụ. | Deny theo contract; side effect không xảy ra. |
| **S09** | Token đúng nhưng tenant khác. | Đọc/ghi resource của tenant khác. | Deny (`403`/`404` theo contract); không lộ dữ liệu. |
| **S10** | PostgreSQL role chỉ SELECT. | Đọc rồi INSERT cùng bảng. | Đọc được, ghi bị từ chối; row count không đổi. |
| **S11** | Redis ACL read-only. | GET rồi SET trên key được cấp phạm vi. | GET được, SET lỗi `NOPERM`; dữ liệu không đổi. |
| **S12** | Kafka/RabbitMQ/Pulsar user thiếu quyền publish/consume. | Gửi/nhận qua adapter thật. | Broker từ chối thao tác, listener không báo xử lý thành công. |
| **S13** | Rotate token hoặc DB password. | Lần đầu sai, sau đó nạp đúng secret. | Hồi phục theo cơ chế refresh/restart rõ ràng; không cần hạ cấp bảo mật. |
| **S14** | Secret sai làm hàng loạt message lỗi. | Kiểm tra consumer retry và backlog. | Retry không khuếch đại vô hạn; message được giữ/quarantine theo policy. |
| **S15** | Bật ghi log HTTP/broker/DB ở mức debug. | Tạo lỗi 401, TLS, DB auth. | Không lộ token, header Authorization, password, private key hoặc connection URL có password. |

### 8.1. Các tiêu chí quan sát bắt buộc

Một test “thất bại như kỳ vọng” phải **đủ bằng chứng**:

1. Lỗi xảy ra đúng **lớp** (TLS handshake, authentication, authorization hoặc network) và được ứng dụng phân loại hợp lý.
2. Không có **side effect** ở DB, HTTP API, cache, broker hoặc adapter sau lời gọi bị từ chối.
3. Không có fallback làm suy yếu chính sách, ví dụ tự đổi HTTPS sang HTTP, trust-all hoặc dùng account admin.
4. Không xuất hiện vòng retry vô hạn/đỉnh tải mới; tổng attempts và timeout được giới hạn, phù hợp hợp đồng phục hồi.
5. Response/log/trace/metrics chỉ chứa **mã lỗi và thông tin chẩn đoán an toàn**, không chứa giá trị secret hoặc private key.
6. Sau khi sửa cấu hình test, một test đối chứng **happy path** chứng minh hệ thống vẫn hoạt động khi đủ trust, credential và quyền.

Test thực tế nên chia thành **unit/contract test của client** (mock status, mapping exception), **integration test với TLS/auth/ACL thật** (Testcontainers hoặc test service) và **end-to-end/staging** (đúng ingress, secret management, network policy). Mock lỗi 403 rất hữu ích để kiểm tra cách client xử lý, nhưng chỉ test qua **resource server có policy thật** mới chứng minh phân quyền đúng.

## 9. Quan sát, xử lý sự cố và tránh lộ secret

Một service tích hợp cần quan sát được bảo mật mà không tự biến hệ thống logging thành kho secret:

| Tín hiệu | Giá trị cho vận hành | Cách ghi an toàn |
|---|---|---|
| TLS handshake failures, certificate expiry | Phát hiện cấu hình sai/rotate chưa hoàn tất. | Endpoint alias, loại lỗi, ngày hết hạn hoặc fingerprint không nhạy cảm khi phù hợp; tránh dump private key. |
| Auth failures (401/DB/broker) | Phát hiện token không hợp lệ, account bị thu hồi. | Provider, loại credential, nhóm lỗi; **không ghi nội dung token/password**. |
| Authorization denials (403/SQL/ACL) | Phát hiện scope/role hoặc principal thiếu quyền. | Principal kỹ thuật phù hợp và resource đã được chuẩn hóa; không log payload nhạy cảm. |
| Retry/reconnect attempts và backlog | Phát hiện vòng retry do config sai, lỗi quyền kéo dài. | Số attempts, exception class chuẩn hóa, adapter, trạng thái hàng đợi. |
| `traceId`, `messageId`, `eventId` | Liên kết lỗi với luồng HTTP/broker/DB và lần xử lý lại. | Áp dụng policy dữ liệu cá nhân, tránh đưa ID giá trị cao vào nhãn metric. |
| Probe readiness/dependency health | Phát hiện process còn sống nhưng kết nối bắt buộc không dùng được. | Probe đọc/chẩn đoán an toàn, không gọi API có side effect. |

Không log `Authorization`, `Cookie`, `Set-Cookie`, secret trong query string, Redis URL `redis://user:password@host`, JDBC URL có credential, SSL keystore password hay dump HTTP body chứa thông tin nhạy cảm. Mã lỗi có thể được lộ qua HTTP API dưới dạng chung như `UPSTREAM_AUTH_CONFIGURATION_ERROR` hoặc `DEPENDENCY_UNAVAILABLE`, còn chi tiết chẩn đoán nên ở log nội bộ có redaction và quyền truy cập hạn chế.

### 9.1. Quy trình xử lý khi kết nối bị từ chối

```mermaid
flowchart TD
    A[Outbound operation thất bại] --> B{Có HTTP status / broker auth response?}
    B -->|Không| C{Lỗi JSSE/TLS hay mạng?}
    C -->|TLS| D[Kiểm tra CA, SAN, expiry, mTLS, store password]
    C -->|Network| E[Kiểm tra DNS, port, routing, timeout]
    B -->|Có| F{Authentication hay authorization?}
    F -->|Authentication| G[Kiểm tra secret, issuer/audience, expiry, rotation]
    F -->|Authorization| H[Kiểm tra principal, resource, scope/ACL/GRANT]
    D --> I[Sửa cấu hình trong test/staging, kiểm thử lại]
    E --> I
    G --> I
    H --> I
    I --> J[Xác nhận thành công và không có side effect trái phép]
```

Trong môi trường có nhiều instance, thay đổi secret hoặc certificate nên được triển khai có kiểm soát, tránh một phần instance dùng trust mới còn phần khác chỉ trust cũ. Tùy yêu cầu bảo mật, có thể có khoảng overlap của certificate/key trong giai đoạn rotate; thời gian chồng lấn phải do chính sách tổ chức quyết định. Việc cấp lại quyền phải dựa trên **least privilege**, không dùng `GRANT ALL` hoặc admin role để giải quyết nhanh một lỗi `permission denied` chưa được phân tích.

## 10. Những lỗi thường gặp khi viết test bảo mật tích hợp

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Dùng `trustAll`/tắt hostname verification cho integration test. | Test xanh ngay cả khi endpoint giả mạo hoặc SAN sai. | Tạo test CA, cấp certificate đúng và kiểm tra ca negative riêng. |
| Chỉ test HTTP 401/403 bằng mock rồi kết luận RBAC của server đúng. | Mock không chạy policy thật. | Có test qua resource server/broker/DB bật authorization thực. |
| Dùng tài khoản admin trong tất cả ca kiểm thử. | Không phát hiện quyền tối thiểu thiếu/được cấp quá rộng. | Tạo principal read-only, producer-only, consumer-only, tenant-specific. |
| Coi sai password keystore là HTTP 401. | Lỗi xuất hiện ở tạo SSL context, trước HTTP. | Phân loại TLS/config, auth và authorization thành nhánh riêng. |
| Chỉ `SELECT 1` để chứng minh quyền database. | Không kiểm tra privilege của bảng và thao tác business. | Query business table, thử một thao tác bị deny, kiểm tra rollback/không mutation. |
| Coi broker connected là có quyền consume/publish. | Quyền trên topic/group/namespace có thể bị từ chối sau handshake. | Thử produce và consume trên resource thật với role có/thiếu quyền. |
| Retry 401/403/TLS validation lỗi liên tục. | Lỗi cấu hình không biến mất theo thời gian ngắn và gây bão request. | Fail fast, alert, sửa config, retry chỉ sau thay credential/policy hợp lệ. |
| Cập nhật Secret trong secret manager rồi giả định client đã dùng mới. | Credential có thể được cache trong bean, connection pool hoặc client lâu sống. | Test cơ chế reload/refresh/restart và chứng minh bằng kết nối mới. |
| Ghi toàn bộ HTTP header/exception chứa secrets để debug. | Bí mật có thể xuất hiện trong log, trace, alert, CI artifact. | Redact có hệ thống; test bằng canary secret để kiểm tra log không chứa. |
| ACK message sau khi chỉ enqueue task vào RAM. | Lỗi TLS/quyền ở task nền làm mất message đã ACK. | ACK sau side effect hoặc sau khi lưu công việc bền vững. |

## 11. Checklist trước khi đưa luồng tích hợp vào production

1. **Xác định hợp đồng kết nối:** HTTPS/TLS version, CA, hostname/SAN, yêu cầu mTLS, cách cấp token/password, scope/ACL cụ thể.
2. **Tách credential và permission:** Có tài khoản test chỉ đọc và tài khoản không có quyền cần thiết để chứng minh deny.
3. **Kiểm thử âm tính TLS:** CA lạ, hostname mismatch, expiry, client certificate thiếu/sai, password truststore/keystore sai.
4. **Kiểm thử âm tính auth:** thiếu/sai/hết hạn token, sai DB/broker password, secret biến môi trường rỗng, rotate secret.
5. **Kiểm thử authorization:** 401 khác 403; DB `SELECT` khác `INSERT`, broker `produce` khác `consume`, ACL cache đúng key pattern.
6. **Chặn fallback không an toàn:** không trust-all, không HTTP downgrade, không tài khoản admin ẩn, không nuốt exception rồi ACK.
7. **Giới hạn retry theo loại lỗi:** không retry cấu hình TLS/secret/permission chưa sửa; chỉ retry lỗi transient có deadline và idempotency.
8. **Bảo vệ dữ liệu:** xác minh side effect bằng repository/broker, giữ trạng thái có thể xử lý lại sau khi sửa lỗi.
9. **Quan sát an toàn:** metric/trace phân loại nhóm lỗi, redaction header/password, readiness thể hiện đúng dependency bắt buộc.
10. **Test đối chứng:** khi certificate, secret và quyền đều đúng, cùng use case phải chạy thành công trên đúng integration stack.

Kiểm thử âm tính tốt phải chứng minh cả **quyền bị từ chối đúng nơi** lẫn **hậu quả an toàn cho dữ liệu**. Đó là cơ sở để một luồng Spring Boot Integration hoạt động đúng dưới cấu hình quyền tối thiểu, khi credential bị thu hồi, TLS certificate đổi và khi hệ thống cần phục hồi sau sự cố.

## Tài liệu tham khảo

- [Spring Boot – SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): cấu hình PEM/JKS bundles, truststore/keystore và cơ chế gắn vào các client được hỗ trợ.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): `RestClient.Builder`, `RestClientSsl`, HTTP client cấu hình qua Boot.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, xử lý status và exception.
- [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): trust/key managers, TLS handshake, hostname/certificate validation.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS protocol, chứng thư, xác minh server và cấu hình an toàn.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lưu trữ, rotation, hạn chế lộ secrets.
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh token, issuer/audience và authorization theo policy.
- [PostgreSQL – GRANT](https://www.postgresql.org/docs/current/sql-grant.html): quyền theo database/schema/table.
- [Redis – ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): ACL theo lệnh và key pattern.
- [Apache Kafka – Authorization and ACLs](https://kafka.apache.org/documentation/#security_authz): quyền trên topic, consumer group và principal.
- [Apache Pulsar – Authorization](https://pulsar.apache.org/docs/next/security-authorization/): quyền produce/consume theo role, namespace/topic.
