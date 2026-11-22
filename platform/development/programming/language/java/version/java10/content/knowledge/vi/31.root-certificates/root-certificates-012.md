# Kiểm thử kết nối TLS bằng chính sách bảo mật hiện hành và chứng thư gốc tin cậy (Java 10+)

## 1. Mục tiêu: kết nối HTTPS phải đúng chính sách, không phải chỉ trả HTTP 200

Ứng dụng Java gọi HTTPS tới API công khai, cổng thanh toán, dịch vụ nội bộ hoặc proxy. Một hôm xuất hiện `SSLHandshakeException`, `PKIX path building failed` hay lỗi `No subject alternative names matching`. Đội vận hành phải tìm được nguyên nhân: chứng thư gốc (root CA) không được tin cậy, thiếu intermediate, sai hostname, hết hạn, thuật toán bị chặn, hay runtime mới đã áp dụng chính sách bảo mật nghiêm ngặt hơn.

**Cách xử lý sai** là viết trust manager chấp nhận mọi chứng thư, bỏ hostname verification, thêm chứng thư bất kỳ từ server vào `cacerts` hoặc bật lại những giao thức yếu chỉ để request trả mã 200. Những cách đó làm mất một phần hoặc toàn bộ khả năng **xác thực danh tính server**.

Bài học này giúp:

1. Hiểu **root CA / trust anchor**, chứng thư trung gian, chứng thư máy chủ và truststore.
2. Kiểm tra HTTPS bằng **đúng JDK/JSSE và security policy** dự kiến triển khai, không chỉ bằng công cụ ngoài.
3. Duy trì **PKIX certificate-path validation**, kiểm tra **DNS/IP trong Subject Alternative Name (SAN)**, thời hạn, mục đích sử dụng, thuật toán TLS.
4. Phân biệt truststore mặc định với truststore riêng cho CA nội bộ.
5. Chạy **positive test** (CA tin cậy + hostname đúng) và **negative tests** (CA chưa tin, hostname sai).
6. Đọc lỗi có hệ thống và thiết kế CI/CD không làm yếu chính sách để “sửa” handshake.

Liên hệ Java 10: **OpenJDK JEP 319 — Root Certificates** đưa bộ root CA mặc định vào bản phân phối OpenJDK, giúp nhiều TLS connection sử dụng trust anchors được cung cấp. Đây là mốc phát triển quan trọng của module Java 10. **Danh sách root, trạng thái distrust và chính sách thuật toán trên một JDK hiện đại không phải bản sao bất biến từ năm Java 10.** Chúng phụ thuộc vendor, phiên bản JDK và các cập nhật.

**Nguyên tắc chính:** client chỉ được tin server khi đã kiểm tra **chuỗi chứng thư, danh tính endpoint và TLS policy** phù hợp. Thành công ở tầng HTTP không thể bù cho các bước xác thực bị tắt.

## 2. Root CA, intermediate, leaf, trust anchor và truststore

Hình dung một đường xác thực chứng thư:

```text
                 TRUSTSTORE CỦA CLIENT
              Trusted root CA / trust anchor
                          |
                          | cấp/ủy quyền chứng thư CA
                          v
                   Intermediate CA
                          |
                          | ký chứng thư server
                          v
                Leaf/server certificate
                          |
                SAN = DNS:api.example.test
                EKU = serverAuth
                Key Usage / validity / signature
                          |
                   HTTPS server
```

| Đối tượng | Công dụng | Những điều phải xác nhận |
| --- | --- | --- |
| **Root CA** | Điểm khởi đầu tin cậy được quản lý | Root có thuộc CA được tổ chức cho phép? |
| **Trust anchor** | Khóa/certificate mà validator được phép kết thúc path tại đó | Nguồn tin, fingerprint, scope, chính sách distrust |
| **Intermediate CA** | Ký leaf hoặc một CA khác trong chain | Signature, BasicConstraints, KeyUsage, path-length, thuật toán |
| **Leaf/server certificate** | Xác thực tên server | SAN DNS/IP, thời gian hiệu lực, EKU serverAuth, chữ ký |
| **Truststore** | Chứa các trust anchors hoặc trusted certificates | Có đúng file và những entry được phê duyệt? |
| **Server keystore** | Chứa private key và certificate chain server | Không được làm lộ private key |
| **TLS handshake** | Thỏa thuận phiên bản giao thức và xác thực peer | TLS version/cipher/chain/hostname phù hợp |

**Root CA không phải leaf certificate.** Thông thường server cung cấp leaf và intermediate cần thiết; client xây dựng một đường chứng thư tới **trust anchor đã được client chọn**. Server không thể tự khiến client tin root lạ chỉ vì đính kèm root ấy vào handshake.

**Trust anchor là một quyết định bảo mật**, không phải đuôi file `.pem` hay `.crt`. Một chứng thư được gửi qua email không trở thành root tin cậy chỉ vì import thành công. Phải có nguồn xác thực độc lập, quy trình phê duyệt và thời hạn quản trị.

Với trust anchor, một số kiểm tra hiệu lực không nhất thiết được áp dụng giống hệt chứng thư nằm trong path (ví dụ root là anchor được tin trực tiếp). **Không suy rằng thời hạn certificate root luôn được validator kiểm tra như thời hạn leaf ở mọi provider.** Quản trị root trust/distrust và xem tài liệu PKIX của runtime cụ thể.

## 3. Một HTTPS client Java kiểm tra những gì?

Khái niệm theo thứ tự:

```text
1. Kết nối đúng DNS/IP và port của URI
2. Client/server thương lượng protocol, cipher, key exchange
3. Server gửi certificate chain
4. TrustManager/PKIX dựng đường dẫn tới trust anchor
5. Kiểm tra signature, thời hạn, constraints, usages, algorithm policy
6. Xác minh hostname/IP của URI với SAN certificate
7. Hoàn tất TLS handshake
8. Gửi request HTTP và nhận response/status
```

Các bước có thể đan xen theo implementation, nhưng **đây là những trách nhiệm cần kiểm chứng**. Nếu TLS thất bại trước khi có HTTP, thay đổi HTTP header hoặc body không sửa được nguyên nhân.

Một root **đúng** chưa đủ nếu leaf có SAN **sai**, intermediate không hợp lệ, server chỉ hỗ trợ cipher bị cấm hoặc policy PKIX từ chối chữ ký. Một certificate chain **đúng** cũng chưa đủ để chứng minh revocation policy được thực hiện; OCSP/CRL tùy cấu hình.

**Đừng dùng “`curl` kết nối được” hoặc “`openssl s_client` có output” làm chứng cứ duy nhất rằng Java TLS policy đã được thỏa mãn**: mỗi công cụ có thể dùng tập root, thư viện TLS và cách kiểm chứng hostname khác.

## 4. Truststore mặc định của SunJSSE: thứ tự tìm kiếm

Theo hướng dẫn JSSE của Oracle, trong trường hợp dùng trust manager mặc định tương ứng, việc tìm trust material thường theo thứ tự:

1. System property `javax.net.ssl.trustStore` được chỉ định → thử mở **đúng file/path đó**.
2. Nếu chưa chỉ định property, ưu tiên `<java-home>/lib/security/jssecacerts` khi có.
3. Nếu không có `jssecacerts`, dùng `<java-home>/lib/security/cacerts` nếu có.
4. Nếu không có nguồn trust phù hợp, không được giả định rằng mọi certificate sẽ được tin; trust manager có thể có tập anchors rỗng.

```text
javax.net.ssl.trustStore được chỉ định?
     |
   Có -----------------> file do ứng dụng chỉ định
     |
   Không
     |
     +-----------------> jssecacerts (nếu có)
     |
     +-----------------> cacerts (khi jssecacerts không có)
```

**Cảnh báo rất quan trọng:** nếu `javax.net.ssl.trustStore` **đã được đặt nhưng file đó không tồn tại**, SunJSSE có thể khởi tạo truststore **rỗng** thay vì quay về `cacerts`. Vì vậy việc thêm một system property sai đường dẫn có thể làm **mọi endpoint công khai trước đây hợp lệ bỗng bị lỗi PKIX**.

**Cài custom truststore thường là thay nguồn trust material mặc định**, không phải tự động cộng thêm CA nội bộ vào toàn bộ root của `cacerts`. Nếu cần cả hai, phải xây truststore đã chọn **tập root cần thiết** hoặc cấu hình client SSLContext kết hợp nguồn một cách có kiểm soát và có test.

**Không mặc định mọi runtime luôn dùng chính file `cacerts`**: vendor, image container, hệ điều hành và provider có thể tùy biến cách lấy CA. Phải kiểm tra `java.home`, cấu hình JVM và truststore hiệu lực bên trong đúng tiến trình/container.

## 5. Kiểm kê các chứng thư gốc của JDK đang dùng

JDK cung cấp `keytool`; kiểm kê truststore mặc định:

```bash
keytool -list -cacerts
```

Lệnh có thể yêu cầu mật khẩu để kiểm tra tính toàn vẹn. Tránh đưa mật khẩu thật vào command line/log. Muốn xem một alias:

```bash
keytool -list -cacerts -alias your-root-alias -v
```

Alias `your-root-alias` là placeholder phải lấy từ store thực tế. Xem chứng thư CA ngoài bằng:

```bash
keytool -printcert -file organization-root.pem -v
```

Trong output, kiểm tra **subject**, **issuer**, **SHA-256 fingerprint**, **validity**, **BasicConstraints**, KeyUsage và các extension liên quan. Root phải được xác minh với **fingerprint lấy từ một kênh tin cậy độc lập**. Fingerprint chỉ xuất hiện cùng file/email ban đầu không đủ để chứng minh nguồn gốc.

**Lưu ý:** `keytool -list -cacerts` cho biết **file cacerts** chứa gì; nếu Java client dùng `javax.net.ssl.trustStore`, `jssecacerts`, provider khác hoặc SSLContext riêng thì output đó **không nhất thiết phản ánh đúng trust anchors client đang dùng**.

**Không sửa global `cacerts` ngay vì một endpoint bị lỗi.** Một thay đổi toàn JDK có thể ảnh hưởng đến nhiều ứng dụng và mở rộng quyền tin cậy. Đối với CA nội bộ, nên ưu tiên truststore riêng theo service, được quản lý trong deployment.

## 6. Java security policy còn bao gồm TLS và certificate-path restrictions

Những security properties quan trọng trong JDK/SunJSSE:

| Property | Phạm vi điển hình |
| --- | --- |
| `jdk.tls.disabledAlgorithms` | TLS protocols, cipher suites, key exchange hoặc thành phần thuật toán bị chặn |
| `jdk.certpath.disabledAlgorithms` | Thuật toán và key sizes không được cho phép khi kiểm tra certificate path |
| Các security properties/provider khác | Cấu hình thuật toán, provider và một số hạn chế crypto khác |

Tập các giá trị phải được lấy từ bản JDK đang triển khai, thường ở:

```text
<java-home>/conf/security/java.security
```

**Phân biệt Java security properties với JVM system properties.** Trong một phương thức Java:

```java
import java.security.Security;

String tlsDisabled =
        Security.getProperty("jdk.tls.disabledAlgorithms");
String certDisabled =
        Security.getProperty("jdk.certpath.disabledAlgorithms");

System.out.println(tlsDisabled != null);
System.out.println(certDisabled != null);
```

Đây là đoạn minh họa trong một phương thức, không phải source file độc lập. Không dùng `System.getProperty("jdk.tls.disabledAlgorithms")` rồi giả định đó là cách luôn lấy chính sách của JSSE.

**TLS 1.3 và TLS 1.2** vẫn là các giao thức chính cho nhiều ứng dụng hiện đại khi provider, server và policy hỗ trợ. Một provider có thể còn triển khai nhận diện tên TLS cũ nhưng các security properties hoặc default settings có thể **chặn** chúng; không nên bật lại SSLv3/TLS 1.0/TLS 1.1 chỉ để test kết nối thành công.

**Chứng thư có root được tin nhưng vẫn có thể bị từ chối** khi algorithm constraints, EKU/KeyUsage, thời hạn hay tên endpoint không hợp lệ. Vì thế không thể “chữa mọi SSLHandshakeException” bằng import CA.

Danh sách disabled algorithms **có thể đổi theo JDK update/vendor**. Không copy nguyên một chuỗi từ blog năm Java 10 vào môi trường Java 17/21/25/27 mà không đánh giá chính sách hiện hành.

## 7. Hostname và Subject Alternative Name: một nhánh kiểm tra độc lập

Giả sử leaf certificate có:

```text
Subject Alternative Name:
  DNS:api.example.test
```

Client kết nối `https://api.example.test` có thể khớp hostname; nhưng kết nối `https://192.0.2.10` **không tự hợp lệ** chỉ vì IP đó dẫn tới cùng server. Chứng thư không có SAN IP tương ứng nên phải bị từ chối khi kiểm tra danh tính đúng cách.

Nguyên tắc:

- Dùng **hostname/IP đúng như trong URI ứng dụng thực tế**.
- Xem SAN DNS/IP của leaf, không chỉ dựa vào `CN=...`.
- Đừng đặt custom `Host` header để giả vờ xác thực một hostname khác ở tầng TLS.
- Đừng dùng JVM flags nội bộ để tắt HTTPS hostname verification.
- Nếu proxy/ingress/service mesh thay TLS termination, cần xác định server nào thực sự trình certificate.

**Import root đúng chưa giải quyết được sai hostname.** Hai điều kiện “tin issuer” và “đúng tên server” độc lập, và bộ test phải chứng minh cả hai.

Đối với DNS production, không tùy tiện chuyển URI sang IP chỉ để tránh phụ thuộc DNS nếu certificate chưa có IP SAN phù hợp. Sửa chính sách cấp chứng thư hoặc cách xác định endpoint thay vì hạ xác thực.

## 8. Test một HTTPS endpoint bằng Java `HttpClient`

Với Java 17+, một chương trình sử dụng **SSLContext mặc định** và để JSSE thực hiện xác minh:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpsCheck {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java HttpsCheck https://host/path");
        }

        URI url = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(url.getScheme())) {
            throw new IllegalArgumentException(
                    "Require an HTTPS URL");
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        System.out.println("httpStatus=" + response.statusCode());
    }
}
```

Biên dịch:

```bash
javac --release 17 HttpsCheck.java
```

Chạy với endpoint HTTPS được phép kiểm thử:

```bash
java HttpsCheck https://your-authorized-service.example/health
```

**Không có stdout cố định** vì status và kết quả kết nối phụ thuộc DNS/network/endpoint/JDK/truststore thực. Nếu nhận được HTTP 401/403/404, TLS đã có thể hoàn tất và sau đó ứng dụng bị từ chối ở tầng HTTP; không mặc định đó là lỗi chứng thư.

Trong Java `HttpClient` mặc định, HTTPS đi qua JSSE và có hostname checking. Bài **không cấu hình custom trust-all manager**. Nếu app production dùng thư viện HTTP khác, cần test thêm bằng **đúng thư viện đó**, kể cả proxy/mTLS settings.

**Không gửi request kiểm thử vào dịch vụ bên thứ ba ngoài phạm vi được phép.** Ưu tiên staging/health endpoint do tổ chức quản lý.

## 9. Truststore riêng cho CA nội bộ: cách làm an toàn

Khi dịch vụ được cấp chứng thư từ một private CA:

1. Nhận trust anchor CA từ kênh PKI có thẩm quyền.
2. Kiểm tra fingerprint SHA-256 từ nguồn độc lập.
3. Xác minh CA constraints và mục đích sử dụng.
4. Tạo **PKCS12 truststore riêng** với những root được phép.
5. Cấu hình ứng dụng dùng store này **trong phạm vi cần thiết**.
6. Test cả endpoint công khai khác nếu client còn cần trust public CA.
7. Định kỳ kiểm tra rotation, expiry, provider changes, quyền file và revocation policy.

Ví dụ, **chỉ sau khi root đã được xác minh**:

```bash
keytool -importcert \
  -alias organization-root \
  -file organization-root.pem \
  -keystore app-trust.p12 \
  -storetype PKCS12
```

`keytool` có thể yêu cầu nhập mật khẩu và xác nhận import. Không dùng `-noprompt` cho chứng thư CA chưa xác thực.

Gắn custom store cho một JVM process:

```bash
java -Djavax.net.ssl.trustStore=/secure/app-trust.p12 \
     -Djavax.net.ssl.trustStoreType=PKCS12 \
     -jar app.jar
```

**Cảnh báo:** lệnh minh họa giả định file, JAR và quyền tồn tại. Mật khẩu thực nếu cần không nên xuất hiện trực tiếp trong lệnh dòng `-Djavax.net.ssl.trustStorePassword=...`, process list hoặc log; dùng cơ chế protected secrets của môi trường.

Nếu ứng dụng có nhiều HTTP clients với yêu cầu trust khác nhau, có thể tạo **SSLContext riêng** cho client gọi private CA thay vì thay global truststore của mọi kết nối JVM. Khi dùng custom store, các root công khai **không được cộng thêm tự động**; cần xác định rõ trust policy của từng client.

## 10. Kiểm thử cả dương tính và âm tính

Ba kịch bản nền tảng:

| Ca | Chứng thư / client | Expected |
| --- | --- | --- |
| A — Untrusted certificate | Server tự ký mới tạo, không có trong default truststore | **Từ chối TLS handshake** |
| B — Trust được cấp có chủ đích | Client có custom truststore chứa test trust anchor; hostname trùng SAN | **Kết nối HTTPS thành công** |
| C — Sai hostname | Vẫn trust anchor B nhưng URI dùng IP/DNS khác SAN | **Từ chối TLS handshake** |

Vì sao phải có A? Nếu client mặc định chấp nhận một chứng thư chưa được trust, có thể môi trường đã import nhầm root hoặc ứng dụng đã gắn trust-all manager.

Vì sao phải có C? Một server đã được tin theo chain **không có nghĩa** server đó được phép nhận request cho mọi hostname. Nếu client tự động chấp nhận cả hostname sai, một phần bảo vệ danh tính đã bị tắt.

Có thể mở rộng bộ test:

- Certificate hết hạn hoặc chưa tới `notBefore`.
- Intermediate CA thiếu; chain không dẫn tới root được tin.
- Leaf chỉ có SAN cho hostname khác.
- Certificate thiếu `serverAuth` EKU hoặc key usage cần thiết.
- Thuật toán/kích thước khóa bị `disabledAlgorithms` từ chối.
- Server chỉ cho protocol/cipher đã bị policy cấm.
- mTLS không có client certificate.
- Certificate rotation với cross-signing hoặc trust anchor mới.
- Revocation qua OCSP/CRL theo policy đã chủ động bật.

**Không giả định JSSE tự kiểm tra mọi trạng thái OCSP/CRL trong mọi cấu hình.** Revocation có chính sách và điều kiện vận hành riêng.

## 11. Fixture thử nghiệm cục bộ: tự tạo certificate cho `localhost`

Để tránh phụ thuộc Internet và dữ liệu CA công khai thay đổi, thực hành tạo **một self-signed leaf cho hostname `localhost`**, mở HTTPS server trên loopback và kiểm tra ba nhánh.

```text
               HTTPS loopback server
               127.0.0.1:<random-port>
               cert SAN: DNS:localhost
               key: server.p12
                        |
          +-------------+--------------+
          |             |              |
          v             v              v
   Default client  Trusted client  Trusted client
    no test root   with trust.p12  URI uses 127.0.0.1
          |             |              |
        REJECT      200 + body ok      REJECT
       no trust       trusted         SAN mismatch
```

**Cảnh báo rõ:** ta sẽ import self-signed **leaf** trực tiếp làm **test trust anchor chỉ trong thư mục tạm**. Đây không phải mô hình PKI production. Không import một leaf bất kỳ từ server lạ để “sửa” kết nối Internet; đối với dịch vụ thật, quản lý root/private CA được xác nhận.

### 11.1. Tạo hai file PKCS12 trong Bash

Các lệnh dùng **Bash/sh**, có `keytool` của JDK 17+, và tạo/xóa tệp **trong thư mục tạm**. Chỉ chạy trong môi trường thử nghiệm được kiểm soát.

```bash
set -e

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Mật khẩu giả, CHỈ dùng cho fixture cục bộ rồi xóa.
TEST_PASSWORD='testOnlyPass123'

keytool -genkeypair \
  -alias server \
  -keyalg RSA -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 2 \
  -keystore "$WORK/server.p12" \
  -storetype PKCS12 \
  -storepass "$TEST_PASSWORD" \
  -keypass "$TEST_PASSWORD" \
  -dname 'CN=localhost,OU=Test,O=Local,C=US' \
  -ext 'SAN=dns:localhost' \
  -ext 'EKU=serverAuth' \
  -noprompt

keytool -exportcert \
  -alias server \
  -rfc \
  -keystore "$WORK/server.p12" \
  -storepass "$TEST_PASSWORD" \
  -file "$WORK/server.pem"

# Chỉ cho fixture tự sinh, không làm với root ngoài chưa xác minh.
keytool -importcert \
  -alias localtest \
  -file "$WORK/server.pem" \
  -keystore "$WORK/trust.p12" \
  -storetype PKCS12 \
  -storepass "$TEST_PASSWORD" \
  -noprompt
```

Đoạn này dùng **RSA 3072 và SHA256withRSA** để tạo fixture hiện đại, không có nghĩa mọi môi trường production phải dùng đúng RSA 3072. Với tổ chức có chính sách crypto riêng, chọn thuật toán/khóa phù hợp yêu cầu và provider.

**SAN chỉ có `DNS:localhost`, không có `IP:127.0.0.1`** là dụng ý: test phải thành công khi URI dùng hostname và thất bại khi dùng IP.

**Không copy mật khẩu cứng** vào sản phẩm. Đây là credential giả của keystore chỉ sống trong test. Trong môi trường thật, dùng secret injection/protected files hoặc cơ chế nhập bí mật được phê duyệt, không ghi private key hoặc password vào repository.

Nếu sử dụng PowerShell, cú pháp nối dòng `\` và `trap` không áp dụng trực tiếp; viết lại thành lệnh PowerShell tương ứng. Không đánh đồng hai shell.

## 12. Chương trình Java 17+ hoàn chỉnh: kiểm tra root trust và SAN

Tạo file `TlsTrustPolicyDemo.java` bên cạnh nơi chạy `javac`:

```java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
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
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.TrustManagerFactory;

public class TlsTrustPolicyDemo {
    // Chỉ cho fixture thử nghiệm cục bộ, không dùng ở production.
    static final char[] PASSWORD =
            "testOnlyPass123".toCharArray();

    static KeyStore read(String file) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (var input = Files.newInputStream(Path.of(file))) {
            store.load(input, PASSWORD);
        }
        return store;
    }

    static SSLContext serverContext(KeyStore store)
            throws Exception {
        var keys = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keys.init(store, PASSWORD);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keys.getKeyManagers(), null, null);
        return context;
    }

    static SSLContext clientContext(KeyStore trusted)
            throws Exception {
        var trust = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trust.init(trusted);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, trust.getTrustManagers(), null);
        return context;
    }

    static HttpRequest request(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(7))
                .GET()
                .build();
    }

    static boolean rejected(HttpClient client, URI uri)
            throws Exception {
        try {
            client.send(
                    request(uri),
                    HttpResponse.BodyHandlers.discarding());
            return false;
        } catch (SSLHandshakeException expected) {
            return true;
        }
    }

    static HttpClient client(SSLContext context) {
        var builder = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(5));

        if (context != null) {
            builder.sslContext(context);
        }
        return builder.build();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Need paths: server.p12 trust.p12");
        }

        HttpsServer server = HttpsServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.setHttpsConfigurator(
                new HttpsConfigurator(
                        serverContext(read(args[0]))));

        server.createContext("/health", exchange -> {
            byte[] body =
                    "ok".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();

            URI good = URI.create(
                    "https://localhost:" + port + "/health");
            URI wrong = URI.create(
                    "https://127.0.0.1:" + port + "/health");

            // Không import test certificate vào default cacerts.
            boolean defaultRejected =
                    rejected(client(null), good);

            // Truststore test chỉ có chứng thư ta vừa tạo.
            HttpClient trusted = client(
                    clientContext(read(args[1])));

            HttpResponse<String> response = trusted.send(
                    request(good),
                    HttpResponse.BodyHandlers.ofString());

            // Root đúng nhưng hostname/IP trong URI không khớp SAN.
            boolean hostnameRejected =
                    rejected(trusted, wrong);

            System.out.println(
                    "defaultRejected=" + defaultRejected);
            System.out.println(
                    "trustedStatus=" + response.statusCode());
            System.out.println(
                    "trustedBody=" + response.body());
            System.out.println(
                    "wrongHostnameRejected=" + hostnameRejected);

            if (!defaultRejected
                    || response.statusCode() != 200
                    || !"ok".equals(response.body())
                    || !hostnameRejected) {
                throw new AssertionError(
                        "TLS policy mismatch");
            }

            System.out.println("tests=PASS");
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch với module HTTP server của JDK và đích Java 17:

```bash
javac --release 17 --add-modules jdk.httpserver \
  TlsTrustPolicyDemo.java
```

Chạy trên cùng shell sau khi đã tạo `WORK/server.p12`, `WORK/trust.p12`:

```bash
java -Djava.net.preferIPv4Stack=true \
  --add-modules jdk.httpserver \
  TlsTrustPolicyDemo \
  "$WORK/server.p12" "$WORK/trust.p12"
```

`java.net.preferIPv4Stack=true` ở đây **chỉ đảm bảo thử nghiệm bind loopback IPv4 ổn định** trên hệ thống ưu tiên IPv6; nó **không vô hiệu hóa TLS/hostname verification**. Không tự động thêm cờ này vào production.

**Output đã biên dịch và chạy kiểm chứng trên Azul Zulu OpenJDK 24.0.2/HotSpot**, dùng keystore/truststore tạm được tạo bằng `keytool`:

```text
defaultRejected=true
trustedStatus=200
trustedBody=ok
wrongHostnameRejected=true
tests=PASS
```

**Giải thích kiểm chứng:**

1. `defaultRejected=true`: client mặc định không tin self-signed leaf ngẫu nhiên do test tạo. Đây là kết quả **fail-closed** đúng kỳ vọng.
2. `trustedStatus=200`: khi dùng `SSLContext` có `TrustManagerFactory` lấy trusted entry test và URI `localhost` khớp SAN, HTTPS thành công.
3. `trustedBody=ok`: HTTP handler thực sự nhận request sau bắt tay TLS và trả response body.
4. `wrongHostnameRejected=true`: dù client đã tin certificate của server, URI dùng IP không có SAN IP phù hợp vẫn bị từ chối.
5. `tests=PASS` chỉ được in nếu cả ba quyết định đúng.

**Phạm vi:** chương trình chứng minh các nhánh trust anchor và hostname verification của **JSSE/HttpClient trong fixture cục bộ**. Nó chưa chứng minh enterprise revocation, CT, pinning, client mTLS, các policy ngoài chuẩn JDK hoặc security audit production.

**Không dùng self-signed leaf test làm CA production**, không dùng mật khẩu tĩnh ở server thật, và không lưu private key fixture sau test.

## 13. Nếu test chạy khác trên một máy khác?

Kết quả có thể bị ảnh hưởng bởi:

- Java vendor, update và security policy.
- JSSE provider bị thay bằng provider tùy chỉnh.
- Thuật toán/key size bị chính sách tổ chức cấm, dù fixture dùng RSA/SHA-256.
- Chính sách Windows IPv4/IPv6, localhost DNS, firewall local.
- Truststore mặc định đã bị tùy chỉnh để tin một chứng thư ngoài phạm vi.
- App dùng proxy và không thật sự kết nối tới server loopback dự kiến.
- Module `jdk.httpserver` không có trong một runtime image rút gọn.

**Không sửa thất bại bằng cách đổi code sang trust-all.** Kiểm tra nguyên nhân, runtime và security properties; nếu môi trường cấm keytool hoặc không thể mở loopback, dùng test environment/CI được thiết kế phù hợp.

Mã thử chỉ được coi là phù hợp khi chạy bằng **JDK 17+** và trong môi trường kiểm soát được. Nếu cần kiểm thử application runtime thực sự, phải dùng đúng image/JAR/dependencies và credential policy của sản phẩm.

## 14. Phân biệt các nhóm lỗi TLS thực tế

| Triệu chứng | Nguyên nhân thường gặp | Bước xử lý |
| --- | --- | --- |
| `PKIX path building failed` | Không có chain dẫn tới trust anchor | Kiểm tra CA, intermediate, truststore đúng path |
| `unable to find valid certification path` | Root không được trust hoặc chain sai | Xác nhận fingerprint và chain; không trust-all |
| `No subject alternative names matching ...` | Hostname/IP không thuộc SAN | Sửa URI hoặc cấp cert có SAN tương ứng |
| `CertificateExpiredException` | Certificate trong path đã hết hạn | Thay/gia hạn cert và kiểm tra đồng hồ |
| `CertificateNotYetValidException` | Chứng thư chưa đến hiệu lực | Kiểm tra thời gian và certificate |
| `Algorithm constraints check failed` | Thuật toán/key size bị policy chặn | Cấp cert/khóa mạnh hơn, cập nhật server |
| `handshake_failure` / `protocol_version` | Không có protocol/cipher chung hoặc auth lỗi | Xem TLS negotiation log; không bật lại protocol yếu |
| mTLS thiếu client cert | Server yêu cầu identity client | Cấu hình key manager/keystore đúng |
| `UnknownHostException` | DNS không phân giải | Kiểm tra DNS, routing, proxy |
| `ConnectException` / timeout | Server/port/firewall/proxy | Kiểm tra network trước khi sửa trust |
| HTTP 401/403/404 sau handshake | TLS có thể hợp lệ, lỗi nằm tầng ứng dụng | Sửa authentication/authorization/route |

Các thông báo có thể **được bọc trong exception khác** hoặc khác chữ theo JDK. Kiểm tra full cause chain và log có kiểm soát. Không quy mọi `SSLHandshakeException` về “Java không nhận root”.

**Bẫy nữa:** endpoint còn hoạt động qua `curl -k` (bỏ xác minh peer) không chứng minh kết nối an toàn. Đó chỉ là một phép thử chẩn đoán network, **không** được tính là QA TLS policy PASS.

## 15. Chẩn đoán bằng JSSE/TLS debug của chính JDK

SunJSSE có các tùy chọn debug vẫn đang được Oracle tài liệu hóa:

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager \
  HttpsCheck https://your-authorized-service.example/health
```

Và khi cần xem các bước certificate path:

```bash
java -Djava.security.debug=certpath \
  HttpsCheck https://your-authorized-service.example/health
```

Điều cần tìm:

- Client thật sự chọn protocol/cipher nào.
- Server gửi những certificate/issuer nào.
- Trust manager có nhận ra trust anchors trong store không.
- Certificate path bị từ chối bởi điều kiện nào.
- Endpoint identity/hostname mismatch nằm ở bước nào.

**Quy tắc sử dụng log:**

- Chỉ bật khi cần, ưu tiên staging hoặc sự cố có giám sát.
- Không bật `all`, record/plaintext dumps hoặc trace nhạy cảm liên tục trong production.
- Không chia sẻ nguyên log chứa hostname nội bộ, certificate chain hoặc secret liên quan.
- Không parse exact wording thành mã xử lý business; debug output **không phải API ổn định**.
- Provider khác SunJSSE có thể không cung cấp cùng tính năng debug.

Có thể xem những default security properties bằng API `Security.getProperty`, nhưng không lấy một chuỗi policy rồi tự nới lỏng ngay tại runtime để ép handshake thành công.

## 16. OpenSSL giúp xem chain, không thay Java certificate validation

Khi được phép chẩn đoán endpoint thuộc quyền quản lý:

```bash
openssl s_client \
  -connect your-authorized-service.example:443 \
  -servername your-authorized-service.example \
  -showcerts -verify_return_error
```

Thông tin nhận được hữu ích để xem server chain, certificate public data và negotiated TLS. Tuy nhiên:

1. OpenSSL có thể dùng root CA store của OS/OpenSSL chứ **không phải JDK cacerts**.
2. Algorithm policy và TLS provider có thể khác JSSE.
3. Không giả định mọi cách gọi `s_client` tự kiểm tra đúng HTTPS hostname.
4. SNI servername không tự đồng nghĩa đã thực hiện đầy đủ hostname verification.
5. Proxy/mesh có thể làm đường kết nối của một lệnh CLI khác JVM thật.

Nếu muốn dùng OpenSSL để kiểm tra hostname cần đặt option tương ứng cho phiên bản công cụ đó, sau đó **vẫn kiểm chứng với Java `HttpClient`**. Một kết quả OpenSSL thành công không đủ kết luận SunJSSE sẽ tin cùng root.

## 17. Revocation qua OCSP/CRL là một chính sách phải được thiết kế

Một certificate path dẫn đến root hợp lệ **không tự chứng minh** rằng client đã kiểm tra trạng thái revoked theo kỳ vọng.

Với Java PKIX, revocation behavior có thể dựa vào:

- `PKIXRevocationChecker` và `PKIXParameters`.
- OCSP/CRL endpoints và việc có thể truy cập từ network.
- Cache, certificate-stapling capability, provider.
- Chính sách **hard-fail** hoặc **soft-fail** khi responder tạm không truy cập được.
- Cấu hình trust manager và security properties của JDK.

**Không tuyên bố “Java mặc định luôn check tất cả OCSP/CRL”**: cần đánh giá cấu hình thực tế. Nếu tổ chức bắt buộc revocation, hãy thiết kế test cho: chứng thư hợp lệ, revoked, responder offline, revocation metadata thiếu; xác định expected outcome rõ.

Cũng không tự động tắt revocation checker để “chữa handshake” nếu chính sách sản phẩm yêu cầu hard-fail. Cần sửa responder/network hoặc trust policy được phê duyệt.

## 18. Truststore khác keystore, đặc biệt trong mTLS

Trong HTTPS thông thường:

- **Server keystore** chứa private key và chain để server chứng minh danh tính.
- **Client truststore** chứa root/anchors để xác minh server.
- Client không cần có private key nếu server không yêu cầu mTLS.

Trong mutual TLS:

- Client còn có **private key/client certificate chain** trong client keystore.
- Server phải xác thực client certificate theo policy của server.
- Cả phía client và server có thể cần cấu hình **trust managers + key managers**.

| Nhu cầu | HTTPS server authentication | mTLS |
| --- | --- | --- |
| Client tin đúng server CA | Có | Có |
| Client kiểm tra server SAN | Có | Có |
| Client có private key/cert để xuất trình | Không bắt buộc | Có |
| Server xác thực client certificate | Không bắt buộc | Có |

**Không import private key server vào truststore client.** Trong fixture test, `server.p12` chứa private key; `trust.p12` chứa chứng thư công khai được tin có chủ đích. Hai mục đích này phải tiếp tục tách trong production.

`javax.net.ssl.keyStore` liên quan client identity khi dùng JSSE mặc định; nó **không thay thế** `javax.net.ssl.trustStore`. Đừng chữa lỗi mTLS bằng cách import thêm root vào sai loại store.

## 19. Quản trị root CA khi nâng JDK và xoay chứng thư

Một CA được tin trong JDK cũ **không mặc định** còn được tin trong JDK mới. Nguyên nhân có thể là:

- Root được thêm/xóa trong `cacerts` theo cập nhật bảo mật/vendor.
- CA bị distrust theo chính sách.
- Thuật toán hay key size không còn đáp ứng rule.
- Server đổi intermediate hoặc root issuer.
- Container image mới không mang cùng truststore của máy phát triển.
- Ứng dụng thay truststore path hoặc tệp bị thiếu khi deploy.

**JEP 319 là mốc Java 10, không phải lời hứa cố định danh sách root cho mọi Java release.** Cập nhật JDK là một thay đổi bảo mật có thể tác động tới TLS handshakes; cần test sớm trước rollout.

Quy trình rotation:

1. Kiểm kê chain hiện tại, CA issuer và danh sách JVM clients.
2. Xác thực root mới bằng kênh PKI độc lập.
3. Kiểm tra runtime images sẽ dùng root cũ/mới như thế nào.
4. Nếu chính sách cho phép, lập giai đoạn overlap/trust hai root khi chuyển đổi.
5. Test cả positive và negative (root cấm vẫn phải bị từ chối).
6. Rollout store/image theo version và sẵn sàng rollback có kiểm soát.
7. Theo dõi SSLHandshakeException rate, không chỉ overall HTTP status.

**Không tải chứng thư CA vừa thấy trong một handshake thất bại rồi import lập tức.** Khi chưa xác thực độc lập, đó có thể là chứng thư của proxy giả hoặc tác nhân độc hại.

## 20. Ma trận CI/CD phù hợp chính sách hiện hành

| Test | Mục tiêu | Expected |
| --- | --- | --- |
| Public endpoint được phép | Default root trust trên image JDK triển khai | Kết nối đúng certificate/host |
| Private CA được cấp phép | Custom truststore + fingerprint đã xác minh | Kết nối thành công |
| Unknown CA | Self-signed mới, chưa trust | **Từ chối** |
| Wrong SAN | Chain tin cậy, URI không nằm trong SAN | **Từ chối** |
| Certificate expiry | Leaf/chain expired | **Từ chối** theo PKIX policy |
| Certificate not yet valid | Đồng hồ và chứng thư không khớp | **Từ chối** |
| Weak signature/key | Không đạt disabledAlgorithms | **Từ chối** |
| Legacy TLS only | Protocol/cipher không cho phép | **Từ chối** |
| Invalid trustStore path | File explicit path không tồn tại | Phát hiện lỗi config, không ngầm fallback |
| Certificate rotation | Đổi root/intermediate theo kế hoạch | Đúng với policy chuyển đổi |
| mTLS missing identity | Server yêu cầu client certificate | Từ chối hoặc lỗi auth đúng policy |
| Revocation | Revoked và responder failure | Theo hard-/soft-fail policy đã định |
| JDK upgrade | Cùng test chạy trên image mới | Positive và negative vẫn chính xác |

Một bộ test chỉ có `200 OK` rất dễ bỏ sót việc vô tình bật trust-all. **Negative tests quan trọng ngang positive tests** để bảo vệ khỏi regression bảo mật.

Khi nâng Java runtime, cần giữ **đúng vendor/build và truststore** ở CI giống production hoặc có ma trận để nhận biết sự khác biệt. Không nên tự tắt một validation chỉ vì test migration thất bại; thay vào đó cập nhật chứng thư/chain/policy có chủ đích.

## 21. Bảo vệ truststore, private keys và mật khẩu

Truststore chứa các quyết định **ai được phép được tin**, nên là tài sản cấu hình bảo mật:

- Chỉ import CA đã được xác thực từ PKI có thẩm quyền.
- Kiểm tra fingerprint SHA-256 qua kênh độc lập.
- Áp quyền file chỉ cho process/user phù hợp.
- Không lưu private key, mật khẩu thật vào Git, log, Dockerfile hay command history.
- Tránh truyền password bí mật trên command line dễ bị quan sát qua process list.
- Dùng secret manager, protected option files hoặc cơ chế an toàn của hạ tầng.
- Kiểm soát cấu hình truststore theo application/deployment chứ không vá thủ công trong container đang chạy.
- Khi đổi root, ghi nhận issuer/fingerprint, lý do, phạm vi và kế hoạch thu hồi.
- Kiểm tra custom truststore có vô tình thay thế public CA root cần thiết không.

Trong ví dụ loopback, `testOnlyPass123` chỉ là **mật khẩu giả của tệp test tạm**, không phải lời khuyên dùng password cố định cho production. Sau khi shell kết thúc, thư mục fixture phải được xóa.

## 22. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “Kết nối HTTPS trả `200` là đủ chứng minh TLS an toàn.” | Có thể đã bỏ trust/hostname verification | Kiểm thử positive và negative |
| “Server gửi root nào Java cũng phải tin.” | Trust anchors do client quản trị | Chỉ tin CA được cấp phép |
| “Có root rồi thì SAN sai không quan trọng.” | Endpoint identity là kiểm tra độc lập | Dùng hostname/cert SAN đúng |
| “`javax.net.ssl.trustStore` tự cộng vào `cacerts`.” | Có thể thay thế source trust mặc định | Thiết kế tập CA tường minh |
| “Path custom store thiếu thì tự rơi về cacerts.” | SunJSSE có thể có truststore rỗng | Sửa đường dẫn/packaging |
| “`keytool -list -cacerts` là đủ biết mọi client trust gì.” | Client có thể dùng custom SSLContext/store/provider | Kiểm tra client thực |
| “Root trong JDK 10 tồn tại mãi trên mọi JDK.” | CA/distrust policy thay theo cập nhật | Kiểm kê vendor/build |
| “Chỉ cần CN đúng, không cần SAN.” | Hostname/IP checks dựa trên SAN theo chuẩn hiện đại | Cấp leaf có SAN hợp lệ |
| “`System.getProperty` đọc đầy đủ Java security policy.” | Security properties khác System properties | `Security.getProperty` |
| “`curl` thành công nghĩa Java phải thành công.” | Truststore/TLS stack có thể khác | Test bằng đúng Java runtime |
| “`openssl s_client` luôn xác minh HTTPS hostname.” | Phụ thuộc options/cách gọi | Xác minh riêng và test lại bằng Java |
| “`SSLHandshakeException` chỉ do thiếu root.” | Còn SAN, EKU, expiry, cipher, mTLS... | Xem cause chain và debug |
| “Bỏ hostname verification để giải quyết cert sai.” | Mất xác thực endpoint | Sửa URI hoặc certificate |
| “Bật TLS1.0 là sửa được lỗi bảo mật.” | Hạ chuẩn an toàn | Nâng server/client |
| “Mọi Java TLS tự kiểm tra revocation đầy đủ.” | Phụ thuộc PKIX/provider và policy | Thiết kế/test OCSP/CRL |
| “KeyStore và TrustStore dùng như nhau.” | Private key identity khác anchors trust | Phân biệt key manager và trust manager |
| “Import self-signed leaf trong test là mô hình production.” | Fixture chỉ trust anchor cục bộ tạm | Dùng PKI được phê duyệt |

## 23. Bài tập tự kiểm tra

### Câu 1. Unknown CA

Một private HTTPS service được ký bằng CA nội bộ nhưng Java client dùng default public `cacerts`.

**Đáp án:** Nếu CA không được trust hoặc chain thiếu intermediate, JSSE không tìm thấy valid path. Xác thực private CA từ nguồn độc lập, cấu hình truststore phù hợp và test với đúng URI. Không dùng trust-all manager.

### Câu 2. Trust root rồi nhưng SAN sai

Client gọi `https://10.0.0.5`; leaf chỉ có `DNS:api.example.test`, chain dẫn tới root tin cậy.

**Đáp án:** Vẫn phải bị từ chối nếu leaf không có IP SAN phù hợp. Trust anchor và hostname là hai điều kiện riêng; sửa URI hoặc cấp certificate phù hợp, không tắt hostname verification.

### Câu 3. Trỏ trustStore tới file không tồn tại

```bash
java -Djavax.net.ssl.trustStore=/missing/app-trust.p12 \
  HttpsCheck https://your-authorized-service.example/health
```

**Đáp án:** Theo SunJSSE, explicit path sai có thể dẫn tới **empty truststore**, không tự dùng `cacerts`. Kiểm tra file/path và image deployment.

### Câu 4. Vì sao `curl` chạy nhưng Java lỗi?

**Đáp án:** Cùng endpoint nhưng **CA store, TLS provider, enabled algorithms hoặc hostname policy khác**. Dùng `openssl` xem chain nếu cần, sau đó test bằng client Java thực.

### Câu 5. Chính sách disabledAlgorithms

Một server sử dụng giao thức/cipher bị `jdk.tls.disabledAlgorithms` chặn, nhưng certificate chain dẫn tới root có trong `cacerts`.

**Đáp án:** Handshake vẫn có thể bị từ chối. Root tin cậy không hợp thức hóa giao thức/thuật toán bị vô hiệu hóa. Cần nâng server TLS.

### Câu 6. Truststore hay keystore cho mTLS?

**Đáp án:** Client truststore chứa CA để kiểm tra server; client keystore chứa private key/client certificate để server kiểm tra client. Trong mTLS có thể cần cả hai; không import server private key vào truststore.

### Câu 7. OCSP/CRL có chắc được check?

**Đáp án:** Không nên mặc định như vậy. Cần cấu hình/trust manager/PKIXRevocationChecker phù hợp và test revoked/responder unavailable theo policy.

### Câu 8. Điểm nào chứng minh test không bỏ hostname verification?

**Đáp án:** Ca A kiểm tra unknown CA bị từ chối, ca B kiểm tra đúng CA và SAN thành công, đặc biệt **ca C dùng cùng truststore nhưng IP khác SAN bị từ chối**. Đây là bằng chứng test không chỉ vô hiệu hóa kiểm tra cert để lấy 200.

## 24. Checklist xác nhận kết nối đạt chính sách bảo mật

1. Xác định **JDK vendor/update/build** và HTTP/TLS stack của ứng dụng thật.
2. Xác nhận URI HTTPS/DNS/IP đúng với endpoint production/staging.
3. Kiểm tra leaf, intermediate chain và trust anchor được phê duyệt.
4. Kiểm tra truststore **JSSE thực sự dùng**, không chỉ file `cacerts` tình cờ tồn tại.
5. Xác minh fingerprint root qua kênh độc lập.
6. Đối chiếu **SAN hostname/IP**, không dựa vào CN đơn thuần.
7. Xác minh thời hạn, EKU/KeyUsage, constraints và algorithm policies.
8. Tôn trọng `jdk.tls.disabledAlgorithms` và `jdk.certpath.disabledAlgorithms` hiện hành.
9. Không bật lại TLS cũ, weak cipher hay trust-all để che lỗi.
10. Chạy **positive test** và ít nhất hai **negative tests** (unknown CA, wrong hostname).
11. Nếu client dùng custom truststore, kiểm tra public roots có bị thay thế ngoài ý định không.
12. Với mTLS, kiểm tra riêng client keystore/private key và server trust policy.
13. Khi cần revocation, kiểm chứng OCSP/CRL và hard-/soft-fail behavior.
14. Dùng JSSE debug vừa đủ, bảo vệ log và tránh ghi bí mật.
15. Không dùng `curl` hay OpenSSL như bằng chứng duy nhất.
16. Phân biệt `PKIX`, SAN, protocol, network và HTTP authorization errors.
17. Test root/chain rotation và JDK update trong CI trước rollout.
18. Không import CA chưa xác thực, không sửa global cacerts tùy tiện.
19. Giữ test fixture tự ký **chỉ ở môi trường test và trong thời gian ngắn**.
20. Chỉ tuyên bố PASS với những điều kiện đã kiểm chứng; một TLS fixture không thay thế toàn bộ security audit.

## Kết luận

Kiểm thử kết nối theo **chính sách bảo mật Java hiện hành** không phải tìm cách làm cho `SSLHandshakeException` biến mất bằng mọi giá. Đó là việc để **JSSE trên đúng JDK/truststore** kiểm tra **PKIX chain**, **trust anchors**, **SAN hostname/IP**, **giao thức và thuật toán TLS được phép**, sau đó xác nhận ứng dụng trao đổi HTTP thành công.

Mốc Java 10 **JEP 319** giúp hiểu nguồn trust anchors mặc định của OpenJDK, nhưng **root list và security policy thay đổi theo thời gian**. Đối với CA riêng, cần một truststore có phạm vi và nguồn tin được quản trị, không import leaf hoặc root từ server không đáng tin.

Chương trình Java 17+ trong bài đã kiểm thử ba nhánh trên cùng HTTPS server loopback: **chứng thư chưa tin bị từ chối; chứng thư được tin và hostname đúng kết nối thành công; hostname sai vẫn bị từ chối**. Đây là cách chứng minh client **fail closed**, không tắt các cơ chế xác thực.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 27 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, trust manager, PKIX, truststore, disabled algorithms và debug.
- [Oracle Java SE 27 — Security Developer's Guide](https://docs.oracle.com/en/java/javase/27/security/): bảo mật Java, JCA/JSSE/PKIX.
- [Oracle Java SE 27 — Java Security Overview](https://docs.oracle.com/en/java/javase/27/security/java-security-overview1.html): root CA, cacerts, JDK keystores và PKCS12.
- [Oracle Java SE 24 — keytool manual](https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html): `-list -cacerts`, fingerprint và thao tác certificate.
- [Java SE 17 — HttpClient API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTPS client với default SSLContext.
- [Java SE 17 — SSLContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): cấu hình key/trust managers.
- [Java SE 17 — TrustManagerFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo trust manager từ KeyStore.
- [Java SE 17 — HttpsServer API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HTTPS loopback server thử nghiệm.
- [Java SE 17 — PKIXRevocationChecker API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): kiểm tra thu hồi theo PKIX.
- [OpenJDK JEP 319 — Root Certificates](https://openjdk.org/jeps/319): mốc bổ sung root certificates trong Java 10.
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certification paths, CA constraints, CRLs.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): xác minh danh tính server theo hostname/IP.
