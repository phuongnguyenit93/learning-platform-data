# Cấu hình HTTPS, CA và xác minh chứng chỉ

Khi ứng dụng Spring Data Elasticsearch kết nối tới một Elasticsearch cluster qua mạng, kết nối cần bảo vệ cả thông tin xác thực lẫn dữ liệu trao đổi. HTTPS sử dụng TLS để mã hóa lưu lượng, xác thực danh tính máy chủ và phát hiện dữ liệu bị thay đổi trên đường truyền. Để xác thực máy chủ thành công, ứng dụng phải tin cậy CA đã ký chứng chỉ và kiểm tra hostname mà nó đang kết nối.

Trong môi trường phát triển đơn giản, ứng dụng có thể kết nối tới `http://localhost:9200`. Với cluster có security hoặc được triển khai trên mạng, endpoint thường là HTTPS, ví dụ `https://es.example.com:9200`. Chỉ đổi `http` thành `https` chưa đủ: JVM cần có CA phù hợp trong truststore, chứng chỉ máy chủ phải hợp lệ với hostname, và client phải giữ cơ chế xác minh TLS mặc định.

Bài học này giải thích cách TLS xác thực Elasticsearch, cách chuẩn bị CA/truststore, cách cấu hình Spring Data Elasticsearch dùng SSL context, cách kiểm tra chứng chỉ và cách xử lý những lỗi thường gặp.

## 1. HTTPS và TLS bảo vệ kết nối như thế nào?

HTTPS là HTTP chạy bên trong một kết nối TLS. Khi client kết nối tới `https://es.example.com:9200`, quá trình TLS handshake diễn ra trước khi request HTTP được gửi:

1. Client mở kết nối TCP tới hostname và port của Elasticsearch.
2. Client và server thương lượng phiên bản TLS, cipher suite và các tham số mật mã có thể sử dụng.
3. Server gửi chứng chỉ TLS cùng các chứng chỉ trung gian cần thiết để xây dựng certificate chain.
4. Client kiểm tra chuỗi chứng chỉ có dẫn tới một CA mà nó tin cậy hay không, chứng chỉ còn hiệu lực hay không và chứng chỉ có phù hợp với hostname được gọi hay không.
5. Hai bên hoàn tất việc thiết lập khóa phiên. Nếu bật mutual TLS (mTLS), server còn yêu cầu client chứng minh danh tính bằng chứng chỉ client.
6. Sau handshake, HTTP request và response được mã hóa, đồng thời được bảo vệ tính toàn vẹn bằng TLS.

```text
Spring Boot application                 Elasticsearch
        |                                     |
        | -------- TCP connection ----------> |
        |                                     |
        | <------ Server certificate -------- |
        |                                     |
        | Validate CA chain, dates, hostname  |
        |                                     |
        | <------ TLS handshake ------------> |
        |                                     |
        | ===== Encrypted HTTP traffic =====> |
        | <==== Encrypted HTTP response ===== |
```

Nếu client không xác thực được chứng chỉ, TLS handshake thất bại và request HTTP chưa được gửi tới Elasticsearch. Đây là lỗi ở lớp TLS, khác với lỗi HTTP `401 Unauthorized` xảy ra sau khi kết nối TLS đã được thiết lập nhưng thông tin xác thực không hợp lệ.

TLS cung cấp ba thuộc tính quan trọng:

- **Confidentiality:** người nghe lén trên đường truyền không đọc được nội dung request/response.
- **Integrity:** dữ liệu bị sửa đổi trên đường truyền sẽ bị phát hiện.
- **Server authentication:** client xác minh đang giao tiếp với máy chủ có danh tính phù hợp với hostname và được CA tin cậy ký chứng chỉ.

TLS không thay thế xác thực và phân quyền Elasticsearch. Ứng dụng vẫn cần tài khoản hoặc API key có quyền tối thiểu cần thiết.

## 2. Phân biệt certificate, CA, truststore và keystore

Các khái niệm này thường xuất hiện cùng nhau nhưng có vai trò khác nhau:

| Thành phần | Ý nghĩa | Dùng ở phía nào? |
|---|---|---|
| Server certificate | Chứng chỉ xác nhận danh tính máy chủ Elasticsearch | Server gửi cho client |
| CA certificate | Chứng chỉ của Certificate Authority dùng để ký hoặc xác thực chuỗi chứng chỉ | Client cần tin cậy CA này |
| Intermediate CA | CA trung gian nối server certificate với root CA | Thường được server gửi trong certificate chain |
| Truststore | Kho các CA/certificate mà ứng dụng chấp nhận làm trust anchor | Client dùng để xác thực server |
| Keystore | Kho private key và certificate của chính một bên | Server hoặc client dùng khi cần chứng minh danh tính |

Trong kết nối TLS một chiều thông thường, ứng dụng Spring Boot chỉ cần truststore chứa CA đáng tin cậy để xác thực chứng chỉ server. Ứng dụng không cần private key của Elasticsearch và cũng không cần một client certificate riêng.

Trong mTLS, mỗi bên xác thực bên còn lại. Client vẫn cần truststore để xác thực server, đồng thời cần keystore chứa client certificate và private key để gửi cho server khi server yêu cầu.

Không nhầm lẫn việc cài CA vào truststore với việc cài server certificate vào keystore. Truststore trả lời câu hỏi “tôi tin cậy CA nào?”, còn keystore trả lời câu hỏi “tôi có khóa riêng và chứng chỉ nào để chứng minh danh tính của mình?”.

## 3. Certificate chain và CA

Một server certificate thường không được ký trực tiếp bởi root CA. Chuỗi chứng chỉ có thể có dạng:

```text
Root CA
   |
   v
Intermediate CA
   |
   v
Elasticsearch HTTP certificate
   |
   v
Hostname: es.example.com
```

Server certificate được ký bởi intermediate CA; intermediate CA lại được ký bởi root CA. Client kiểm tra chữ ký theo chuỗi cho tới khi gặp một CA đáng tin cậy trong truststore. Server thường cần gửi cả server certificate và các intermediate certificate liên quan. Root CA thường đã có trong truststore nên không nhất thiết phải được gửi cùng handshake.

Một CA certificate công khai không phải bí mật. Tuy vậy, cần lấy nó từ nguồn đáng tin cậy và xác minh fingerprint hoặc checksum theo kênh độc lập khi quy trình triển khai yêu cầu. Nếu kẻ tấn công thay CA trong truststore bằng CA do họ kiểm soát, client có thể chấp nhận chứng chỉ giả được CA đó ký.

Đối với Elastic Cloud, deployment cung cấp endpoint HTTPS và thông tin CA cần thiết theo hướng dẫn của dịch vụ. Với Elasticsearch tự quản lý, CA HTTP có thể được tạo trong quá trình cấu hình security hoặc bằng công cụ `elasticsearch-certutil`. Trong cả hai trường hợp, ứng dụng cần đúng CA đã ký certificate chain mà endpoint gửi về.

## 4. Hostname verification và Subject Alternative Name

Tin cậy CA chưa đủ để xác thực máy chủ. Client còn phải xác minh hostname trong URL khớp với danh tính được ghi trong chứng chỉ. Ví dụ, khi kết nối `https://es.example.com:9200`, chứng chỉ cần có Subject Alternative Name (SAN) phù hợp với `es.example.com`.

SAN có thể chứa DNS name hoặc địa chỉ IP. Nếu ứng dụng gọi bằng IP `https://10.0.0.15:9200`, chứng chỉ cần có SAN kiểu IP tương ứng. Một chứng chỉ chỉ có SAN `DNS:es.example.com` không tự động hợp lệ khi client gọi bằng địa chỉ IP, dù IP đó đang trỏ tới cùng máy chủ.

Các tình huống hostname mismatch thường gặp:

- Chứng chỉ được cấp cho `es.internal.example.com` nhưng cấu hình ứng dụng gọi `localhost`.
- Chứng chỉ có DNS SAN nhưng ứng dụng kết nối trực tiếp bằng IP.
- Load balancer hoặc proxy thay đổi hostname mà client sử dụng.
- Chứng chỉ cũ không chứa hostname mới sau khi endpoint được đổi tên.

Hãy dùng hostname DNS nằm trong SAN của certificate và cấu hình DNS/load balancer phù hợp. Không giải quyết lỗi bằng cách tắt hostname verification hoặc dùng `NoopHostnameVerifier`; khi đó client có thể kết nối tới máy chủ giả mạo dù CA chain có vẻ hợp lệ.

## 5. Chuẩn bị CA cho ứng dụng

Trước khi cấu hình Spring, cần lấy CA certificate đã ký chứng chỉ HTTP của Elasticsearch. Tên file thường gặp trong một số cài đặt Elasticsearch tự quản lý là `http_ca.crt`, nhưng đường dẫn cụ thể phụ thuộc cách triển khai. Với dịch vụ được quản lý, tải CA theo hướng dẫn của nhà cung cấp.

Không sao chép private key của CA vào ứng dụng. Ứng dụng client chỉ cần CA certificate công khai để xác thực server.

### 5.1. Kiểm tra thông tin certificate

Nếu có OpenSSL, có thể xem thông tin certificate:

```bash
openssl x509 -in http_ca.crt -noout -subject -issuer -dates -fingerprint -sha256
```

Lệnh cho biết subject, issuer, thời hạn và SHA-256 fingerprint. So sánh fingerprint với giá trị được công bố qua kênh đáng tin cậy trước khi đưa CA vào truststore.

Để xem SAN của server certificate (nếu có file certificate server):

```bash
openssl x509 -in http.crt -noout -text
```

Tìm phần `X509v3 Subject Alternative Name` và xác nhận hostname ứng dụng sử dụng nằm trong danh sách đó.

### 5.2. Tạo truststore PKCS12 bằng keytool

JDK đi kèm công cụ `keytool`, có thể tạo truststore PKCS12 và import CA certificate:

```bash
keytool -importcert \
  -alias elasticsearch-http-ca \
  -file http_ca.crt \
  -keystore elasticsearch-truststore.p12 \
  -storetype PKCS12
```

`keytool` sẽ yêu cầu nhập mật khẩu truststore và xác nhận import certificate. Kiểm tra nội dung sau khi tạo:

```bash
keytool -list -v \
  -keystore elasticsearch-truststore.p12 \
  -storetype PKCS12
```

Truststore chỉ chứa CA certificate công khai nên không cần bảo vệ như private key, nhưng mật khẩu vẫn cần được quản lý để kiểm soát việc sửa đổi truststore. Không commit truststore hoặc mật khẩu môi trường thật vào repository nếu chính sách của tổ chức không cho phép.

Có thể đặt truststore trong thư mục cấu hình được mount vào ứng dụng, hoặc đóng gói CA certificate/truststore phù hợp với quy trình phát hành. Trong môi trường container/Kubernetes, thường mount file và cấp mật khẩu qua secret.

### 5.3. Dùng CA PEM trực tiếp hay truststore?

Một số client hoặc cấu hình SSL hỗ trợ đọc trực tiếp CA certificate dạng PEM. Những cấu hình Java khác yêu cầu truststore dạng JKS hoặc PKCS12. Chọn định dạng được client và phiên bản framework hỗ trợ.

PKCS12 là định dạng trao đổi phổ biến và được JDK hỗ trợ. Nếu ứng dụng có nhiều CA cần tin cậy, có thể import nhiều certificate vào cùng truststore với alias riêng. Chỉ thêm CA thực sự cần thiết; không nhập tùy tiện mọi certificate nhận được từ một kết nối không xác thực.

## 6. Kiểm tra HTTPS trước khi cấu hình Spring Boot

Trước tiên, kiểm tra kết nối từ môi trường chạy ứng dụng. Điều này giúp xác định CA và endpoint đúng trước khi điều tra cấu hình Java.

Với `curl`, chỉ định CA certificate:

```bash
curl --cacert http_ca.crt https://es.example.com:9200
```

Nếu Elasticsearch yêu cầu Basic Authentication, có thể cung cấp username để curl hỏi mật khẩu:

```bash
curl --cacert http_ca.crt \
  --user elastic \
  https://es.example.com:9200
```

Không đưa mật khẩu thật trực tiếp vào lịch sử shell hoặc command line dùng chung. Dùng cơ chế secret phù hợp với môi trường thực tế.

Có thể kiểm tra TLS handshake bằng OpenSSL:

```bash
openssl s_client \
  -connect es.example.com:9200 \
  -servername es.example.com \
  -CAfile http_ca.crt \
  -verify_hostname es.example.com \
  -verify_return_error
```

`-servername` gửi SNI để server hoặc load balancer chọn đúng certificate; `-CAfile` chỉ định CA cần tin cậy; `-verify_hostname` kiểm tra hostname. Khi xác minh thành công, OpenSSL hiển thị kết quả xác minh certificate chain thành công. Lệnh này kiểm tra TLS; nó không thay thế việc thử request ứng dụng với thông tin xác thực Elasticsearch.

Tránh dùng `curl -k` hoặc `--insecure` như cấu hình lâu dài. Các tùy chọn này bỏ qua xác minh chứng chỉ, khiến kiểm thử có thể thành công ngay cả khi ứng dụng đang kết nối tới một máy chủ không đáng tin cậy.

## 7. Cấu hình Spring Data Elasticsearch với SSLContext

Spring Data Elasticsearch cung cấp `ClientConfiguration` để mô tả endpoint, xác thực và SSL cho client. Khi cần dùng CA riêng, ứng dụng có thể tạo `SSLContext` với truststore chứa CA rồi truyền context này vào `ClientConfiguration`.

Ví dụ dưới đây minh họa cách nạp truststore PKCS12 bằng API chuẩn của Java:

```java
import java.io.InputStream;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class ElasticsearchSslContextFactory {

    private ElasticsearchSslContextFactory() {
    }

    public static SSLContext fromTrustStore(
            InputStream trustStoreInput,
            char[] trustStorePassword) throws Exception {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        trustStore.load(trustStoreInput, trustStorePassword);

        TrustManagerFactory trustManagerFactory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trustManagerFactory.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(null, trustManagerFactory.getTrustManagers(), null);
        return sslContext;
    }
}
```

`KeyStore` đọc CA certificate từ truststore. `TrustManagerFactory` tạo trust managers có nhiệm vụ xác thực certificate chain. `SSLContext` tập hợp cấu hình TLS để client sử dụng. Tham số `null` ở vị trí `KeyManager[]` có nghĩa là ví dụ này không cung cấp client certificate; nó phù hợp với TLS một chiều.

Không tạo trust manager chấp nhận mọi certificate. Cũng không thay hostname verifier bằng implementation luôn trả về `true`. Hai cách đó làm mất chính cơ chế xác thực danh tính máy chủ mà HTTPS cần cung cấp.

### 7.1. Tích hợp SSLContext với ClientConfiguration

Với cấu hình client theo kiểu Spring Data Elasticsearch, có thể dùng `ElasticsearchConfiguration` và trả về `ClientConfiguration`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

import javax.net.ssl.SSLContext;

@Configuration
public class ElasticsearchClientConfig extends ElasticsearchConfiguration {

    private final SSLContext sslContext;

    public ElasticsearchClientConfig(SSLContext sslContext) {
        this.sslContext = sslContext;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("es.example.com:9200")
                .usingSsl(sslContext)
                .withBasicAuth("${ES_USERNAME}", "${ES_PASSWORD}")
                .build();
    }
}
```

Đoạn trên minh họa cách ghép SSL context với client cấu hình thủ công. Trong ứng dụng thật, không viết placeholder `${ES_USERNAME}` và `${ES_PASSWORD}` như chuỗi literal trong Java. Hãy inject credential từ cấu hình Spring hoặc secret manager, và tạo `SSLContext` từ resource/mật khẩu được inject tương tự. Cũng cần đảm bảo các bean cấu hình client này thay thế đúng cơ chế auto-configuration đang dùng; không khai báo song song hai cấu hình tạo cùng một Elasticsearch client.

Tên package và API cấu hình có thể thay đổi giữa các major/minor release của Spring Data Elasticsearch. Hãy đối chiếu Javadoc/tài liệu đúng phiên bản trong dự án, đặc biệt khi nâng cấp client. Mấu chốt của cấu hình là `ClientConfiguration` phải dùng HTTPS và nhận `SSLContext` được xây dựng từ CA đáng tin cậy.

### 7.2. Ví dụ cấu hình bằng application.yml

Đưa các giá trị môi trường ra khỏi mã nguồn:

```yaml
app:
  elasticsearch:
    host: ${ELASTICSEARCH_HOST:es.example.com}
    port: ${ELASTICSEARCH_PORT:9200}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    truststore: ${ELASTICSEARCH_TRUSTSTORE:file:/run/secrets/elasticsearch-truststore.p12}
    truststore-password: ${ELASTICSEARCH_TRUSTSTORE_PASSWORD}
```

Đây là namespace cấu hình riêng của ứng dụng dùng cho ví dụ client tùy chỉnh; các thuộc tính này không phải thuộc tính chuẩn `spring.elasticsearch.*`. Lớp cấu hình cần bind chúng bằng `@ConfigurationProperties` hoặc inject tương ứng, mở truststore từ resource đã khai báo và tạo SSL context.

Khi chạy trong container, đường dẫn `/run/secrets/elasticsearch-truststore.p12` cần được mount vào container. Với triển khai khác, thay đường dẫn bằng vị trí truststore thực tế. Không đặt mật khẩu thật trong file YAML được commit.

## 8. Dùng SSL bundle của Spring Boot

Một số phiên bản Spring Boot cung cấp SSL bundle để quản lý truststore/keystore tập trung và cho phép các tích hợp sử dụng bundle đó. Cách cấu hình SSL bundle và việc Elasticsearch Rest Client có property liên kết trực tiếp tới bundle phụ thuộc phiên bản Spring Boot cụ thể.

Khi phiên bản đang dùng hỗ trợ liên kết SSL bundle cho Elasticsearch client, cấu hình theo đúng property metadata và tài liệu của phiên bản đó. Ví dụ, phần định nghĩa bundle dạng JKS/PKCS12 có thể có cấu trúc như sau:

```yaml
spring:
  ssl:
    bundle:
      jks:
        elasticsearch:
          truststore:
            location: file:/run/secrets/elasticsearch-truststore.p12
            password: ${ELASTICSEARCH_TRUSTSTORE_PASSWORD}
            type: PKCS12
```

Tên bundle trong ví dụ là `elasticsearch`. Cấu hình này khai báo trust material cho bundle; bản thân nó không đảm bảo Elasticsearch client tự sử dụng bundle. Cần cấu hình property tích hợp SSL bundle mà đúng phiên bản Spring Boot cung cấp, hoặc đăng ký customizer/client configuration theo API phiên bản đó.

Nếu Spring Boot version không có tích hợp SSL bundle cho Elasticsearch client, có thể dùng cách tạo `SSLContext` và cấu hình `ClientConfiguration` ở phần trước. Không trộn một custom client configuration với auto-configuration mặc định nếu chưa xác định rõ bean nào được sử dụng.

## 9. Khi nào cần mutual TLS?

Trong TLS một chiều, client xác thực server bằng CA. Server không yêu cầu chứng chỉ riêng của client; ứng dụng thường xác thực bằng Basic Authentication hoặc API key sau khi TLS handshake hoàn tất.

Trong mutual TLS, server yêu cầu client gửi certificate. Khi đó, ứng dụng cần:

1. Truststore chứa CA dùng để xác thực server.
2. Keystore chứa client certificate và private key tương ứng.
3. Cấu hình TLS context với cả `KeyManager[]` và `TrustManager[]`.
4. Elasticsearch hoặc proxy phía trước được cấu hình để tin cậy CA đã cấp client certificate và ánh xạ certificate sang quyền truy cập phù hợp.

Ví dụ khởi tạo SSLContext cho mTLS ở mức JDK:

```java
KeyStore clientKeyStore = KeyStore.getInstance("PKCS12");
try (InputStream input = clientKeyStoreResource.getInputStream()) {
    clientKeyStore.load(input, clientKeyStorePassword.toCharArray());
}

KeyManagerFactory keyManagerFactory = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagerFactory.init(clientKeyStore, clientKeyPassword.toCharArray());

KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = trustStoreResource.getInputStream()) {
    trustStore.load(input, trustStorePassword.toCharArray());
}

TrustManagerFactory trustManagerFactory = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagerFactory.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        keyManagerFactory.getKeyManagers(),
        trustManagerFactory.getTrustManagers(),
        null);
```

Đoạn code là phần tạo SSL context; cần truyền context đó vào cấu hình Elasticsearch client như phần trước. Keystore chứa private key là tài sản nhạy cảm. Hạn chế quyền đọc file, không ghi private key hoặc password vào log, và xoay vòng certificate theo chính sách bảo mật.

Không bật mTLS chỉ vì server có HTTPS. Chỉ cấu hình client certificate khi cluster hoặc gateway thực sự yêu cầu nó.

## 10. Xác thực TLS khác với xác thực Elasticsearch

Hai lớp xác thực này độc lập:

| Lớp | Câu hỏi được trả lời | Cơ chế |
|---|---|---|
| TLS server authentication | Client có đang kết nối đúng máy chủ không? | CA chain, thời hạn, SAN/hostname verification |
| TLS client authentication (nếu bật mTLS) | Client có chứng chỉ được server chấp nhận không? | Client certificate và CA mà server tin cậy |
| Elasticsearch authentication | Request thuộc về user/service account nào? | Basic Authentication, API key hoặc cơ chế xác thực được cấu hình |
| Elasticsearch authorization | Danh tính đó được phép làm gì? | Roles, privileges và quyền trên cluster/index |

Ví dụ, TLS handshake có thể thành công nhưng Elasticsearch trả `401 Unauthorized` vì username/password sai. Ngược lại, username/password đúng vẫn không giúp ứng dụng vượt qua lỗi `PKIX path building failed`, vì request chưa đi qua được bước TLS.

Với ứng dụng production, cấp tài khoản riêng cho service và chỉ cấp quyền cần thiết trên index. Không dùng tài khoản `elastic` quản trị cho mọi thao tác của ứng dụng.

## 11. Xử lý lỗi TLS thường gặp

| Thông báo hoặc triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `PKIX path building failed` | JVM không xây dựng được certificate chain tới CA đáng tin cậy | Kiểm tra CA, truststore, certificate chain và truststore mà process thực sự nạp |
| `unable to find valid certification path` | Thiếu CA/intermediate hoặc truststore không đúng | Lấy đúng CA từ nguồn tin cậy, import vào truststore và kiểm tra cấu hình đường dẫn |
| `No subject alternative DNS name matching ...` | Hostname trong URL không khớp SAN của certificate | Dùng hostname có trong SAN hoặc cấp lại certificate có SAN đúng |
| `CertificateExpiredException` | Certificate đã hết hạn | Gia hạn/cấp lại certificate và cập nhật chain/trust material |
| `CertificateNotYetValidException` | Thời gian hệ thống sai hoặc certificate có hiệu lực trong tương lai | Kiểm tra đồng hồ hệ thống/NTP và thời hạn certificate |
| `handshake_failure` | Hai bên không thống nhất được TLS/cipher hoặc mTLS không hợp lệ | Kiểm tra phiên bản TLS, cipher, client certificate và cấu hình server/proxy |
| `unknown_ca` | Bên nhận không tin cậy CA của certificate bên kia | Kiểm tra truststore phía tương ứng và CA phát hành certificate |
| `401 Unauthorized` | TLS đã thành công nhưng thông tin xác thực Elasticsearch không hợp lệ/thiếu | Kiểm tra Basic Auth/API key và quyền truy cập |
| `Connection refused` hoặc timeout | Endpoint, port, DNS, firewall hoặc node chưa sẵn sàng | Kiểm tra mạng và trạng thái Elasticsearch trước khi điều tra certificate |

### 11.1. Kiểm tra đúng truststore đang được sử dụng

Một lỗi phổ biến là đã tạo truststore đúng nhưng ứng dụng vẫn đọc truststore khác hoặc không đọc file nào. Kiểm tra:

- Đường dẫn được resolve từ bên trong process/container, không phải từ máy host.
- File được mount đúng và user chạy JVM có quyền đọc.
- Store type khai báo khớp định dạng file, ví dụ `PKCS12`.
- Mật khẩu truststore đúng.
- CA trong truststore là CA đã ký certificate chain của endpoint đang kết nối.
- Ứng dụng thực sự dùng SSL context/client bean được cấu hình, không vô tình dùng client auto-configured khác.

Trong môi trường kiểm thử có thể bật log TLS của JVM để chẩn đoán handshake. Log TLS có thể chứa thông tin chi tiết về certificate và kết nối, vì vậy chỉ bật tạm thời, giới hạn quyền truy cập và tắt sau khi điều tra.

## 12. Quản lý certificate trong môi trường vận hành

TLS là cấu hình cần được vận hành liên tục. Certificate có thời hạn và CA có thể được thay thế, vì vậy ứng dụng cần quy trình cập nhật trust material.

### 12.1. Xoay vòng CA

Khi chuyển từ CA cũ sang CA mới, có thể triển khai theo giai đoạn:

1. Thêm CA mới vào truststore của ứng dụng trong khi vẫn giữ CA cũ.
2. Phát hành hoặc chuyển server certificate sang CA mới.
3. Xác minh các instance ứng dụng đều kết nối được bằng certificate mới.
4. Sau khi không còn server nào dùng CA cũ, loại bỏ CA cũ khỏi truststore ở lần phát hành tiếp theo.

Cách triển khai này tránh khoảng thời gian ứng dụng không tin cậy certificate đang được server sử dụng. Quy trình cụ thể cần phối hợp với cách cluster, load balancer và ứng dụng rollout certificate.

### 12.2. Theo dõi hạn certificate

Theo dõi ngày bắt đầu và ngày hết hạn của server certificate, intermediate CA, client certificate nếu dùng mTLS và các certificate liên quan. Đặt cảnh báo trước khi hết hạn đủ lâu để có thời gian phát hành, phân phối và kiểm thử certificate mới.

### 12.3. Quản lý secret và file

- Lưu mật khẩu truststore, keystore và private key trong secret manager hoặc secret store của nền tảng.
- Hạn chế quyền đọc file truststore/keystore theo nguyên tắc quyền tối thiểu.
- Không ghi password, private key hoặc nội dung secret vào log.
- Không đưa private key hoặc credential thật vào Git.
- Mount certificate và truststore theo cách có thể cập nhật khi xoay vòng.
- Kiểm tra việc reload cấu hình: một số client chỉ nạp SSL context lúc khởi tạo. Sau khi thay truststore, có thể cần tạo lại client hoặc restart ứng dụng theo cơ chế triển khai.

## 13. Khuyến nghị khi cấu hình HTTPS cho Spring Data Elasticsearch

Khi triển khai ứng dụng, nên tuân theo các nguyên tắc sau:

- Dùng `https://` cho endpoint có TLS và hostname khớp SAN của server certificate.
- Tin cậy đúng CA đã được xác minh; giữ certificate chain đầy đủ.
- Duy trì certificate validation và hostname verification mặc định của client.
- Dùng truststore riêng hoặc SSL bundle được phiên bản Spring Boot hỗ trợ khi cần CA nội bộ.
- Chỉ cấu hình keystore/client certificate khi hệ thống yêu cầu mTLS.
- Đưa endpoint, username, password và mật khẩu truststore ra cấu hình ngoài mã nguồn.
- Giữ TLS version/cipher ở mức an toàn do JDK và Elasticsearch hỗ trợ; không hạ cấp TLS chỉ để né lỗi handshake.
- Phân biệt lỗi TLS, lỗi xác thực HTTP và lỗi phân quyền để xử lý đúng lớp.
- Có kế hoạch xoay vòng CA/certificate và kiểm thử trước khi certificate cũ hết hạn.

## 14. Quy trình triển khai tham khảo

Một quy trình cấu hình kết nối HTTPS từ Spring Boot tới Elasticsearch có thể thực hiện như sau:

1. Lấy endpoint HTTPS và CA certificate từ quản trị viên cluster hoặc nhà cung cấp dịch vụ.
2. Xác minh nguồn gốc và fingerprint của CA; kiểm tra SAN và thời hạn server certificate.
3. Kiểm tra endpoint bằng `curl --cacert` hoặc OpenSSL với hostname verification.
4. Tạo truststore PKCS12 từ CA nếu client cần truststore Java.
5. Cấp truststore vào môi trường chạy ứng dụng và đưa mật khẩu vào secret manager.
6. Cấu hình Spring Data Elasticsearch dùng SSL context chứa trust manager từ truststore, hoặc dùng tích hợp SSL bundle được phiên bản Spring Boot hỗ trợ.
7. Cấu hình xác thực Elasticsearch riêng bằng Basic Auth/API key; chỉ thêm client certificate nếu bật mTLS.
8. Khởi động ứng dụng và xác minh request thực tế thành công qua HTTPS.
9. Theo dõi hạn certificate và chuẩn bị quy trình xoay vòng CA.

Khi đã cấu hình đúng, Spring Data Elasticsearch vẫn cung cấp các thao tác repository và query như bình thường. HTTPS và CA xử lý lớp bảo mật của kết nối bên dưới; entity, mapping và cách gọi repository không cần thay đổi chỉ vì endpoint chuyển từ HTTP sang HTTPS.
