# Yêu cầu chứng thư theo tên miền, SAN và TTL bằng Spring Vault

## 1. Mục tiêu và tình huống thực tế

Trong hệ thống Java dùng HTTPS hoặc mTLS, mỗi dịch vụ cần **chứng thư X.509** xác nhận danh tính của nó. **HashiCorp Vault PKI Secrets Engine** có thể cấp chứng thư từ một CA đã cấu hình, còn **Spring Vault** cho phép Java gọi Vault qua **VaultTemplate/VaultOperations** bằng danh tính workload. Nhờ đó, dịch vụ có thể yêu cầu chứng thư cho tên miền được phép, các tên thay thế (**SAN**) và thời hạn sử dụng (**TTL**) mà không phải cấu hình một chứng thư tĩnh lâu dài.

Bài học này tập trung vào yêu cầu cấp chứng thư, với ví dụ nội bộ:

- **Common Name (CN):** api.example.internal.
- **DNS Subject Alternative Names (DNS SAN):** api.example.internal và api-alt.example.internal.
- **TTL mong muốn:** 12 giờ.
- **PKI mount:** pki; **role cấp chứng thư:** server-int.
- **Ứng dụng:** một dịch vụ Spring Boot cần chứng thư máy chủ TLS.

Các tên miền chỉ dùng để minh họa. Trong môi trường thật, thay bằng những DNS name mà ứng dụng thực sự phục vụ và mà vai trò PKI cho phép.

Sau bài này, bạn sẽ hiểu cách cấu hình chính sách cấp phát ở Vault, dùng **VaultPkiOperations.issueCertificate(...)**, đọc thời hạn thực tế trên chứng thư, xác minh DNS SAN và tránh làm lộ private key.

## 2. Ba tham số chính: CN, SAN và TTL

| Tham số | Ý nghĩa khi cấp chứng thư | Lưu ý |
| --- | --- | --- |
| **CN / common_name** | Tên định danh trong phần Subject của chứng thư, ví dụ api.example.internal. | Các TLS client hiện đại chủ yếu kiểm tra hostname trong **SAN**; chỉ có CN là chưa đủ cho nhiều trường hợp. |
| **DNS SAN / alt_names** | Danh sách DNS name khác hoặc bổ sung mà chứng thư cho phép dùng, ví dụ api-alt.example.internal. | Từng tên phải phù hợp với policy của **PKI role**. Trong ví dụ, đưa cả CN vào DNS SAN để kiểm tra hostname minh bạch. |
| **IP SAN / ip_sans** | Địa chỉ IP được đưa vào Subject Alternative Name. | Chỉ dùng nếu thực sự kết nối bằng IP và role cho phép; IP không phải DNS SAN. |
| **URI SAN / uri_sans** | Danh tính dạng URI, đôi khi sử dụng trong hệ thống service identity. | Cần chính sách URI SAN thích hợp ở role. |
| **TTL** | Khoảng thời gian chứng thư được yêu cầu có hiệu lực, ví dụ 12h. | Chịu ràng buộc bởi TTL tối đa của role, cấu hình PKI và thời hạn CA/issuer. |

**CN không thay thế cho SAN.** Khi client kết nối tới **api-alt.example.internal**, nó kiểm tra tên này có nằm trong DNS SAN của chứng thư hay không. Dù CN là **api.example.internal**, kết nối tới tên phụ vẫn hợp lệ về khía cạnh tên miền nếu SAN có tên phụ và chuỗi tin cậy cùng các điều kiện TLS khác đều đạt.

**TTL không phải TTL của Vault token.** Token ứng dụng có thời hạn và chính sách truy cập riêng; thời hạn chứng thư nằm trong hai trường X.509 **notBefore** và **notAfter**. Token hết hạn không làm chứng thư đã được cấp lập tức hết hạn; ngược lại, chứng thư hết hạn cũng không làm token tự hết hạn.

### Luồng yêu cầu cấp chứng thư

~~~mermaid
sequenceDiagram
    participant Workload as Spring Boot workload
    participant Spring as VaultTemplate / VaultPkiOperations
    participant Vault as Vault PKI
    participant TLS as TLS listener

    Workload->>Spring: CN + DNS SAN + TTL (12h)
    Spring->>Vault: POST /v1/pki/issue/server-int
    Note over Spring,Vault: Token workload có quyền update path issue
    Vault->>Vault: Kiểm tra role, SAN, TTL, issuer
    Vault-->>Spring: Certificate + private_key + CA chain
    Spring-->>Workload: CertificateBundle
    Workload->>Workload: Kiểm tra SAN và notAfter
    Workload->>TLS: Cài chứng thư và private key an toàn
~~~

Điểm quan trọng là **role ở Vault quyết định tên nào được phép cấp**. Không được suy luận rằng ứng dụng có thể yêu cầu bất kỳ CN, SAN hoặc TTL nào chỉ vì nó đã xác thực thành công vào Vault.

## 3. Chuẩn bị PKI engine, issuer và role

Ví dụ giả định quản trị viên đã bật **pki** và cấu hình một CA/issuer có khả năng ký chứng thư cho **example.internal**. Cách dựng root CA, intermediate CA, chuỗi tin cậy, CRL và OCSP thuộc phần quản trị PKI; trong môi trường thật nên sử dụng quy trình CA/issuer được tổ chức phê duyệt.

Để kiểm tra mount khi có quyền quản trị:

~~~bash
vault secrets list

# Chỉ thực hiện bước này nếu mount pki chưa tồn tại:
vault secrets enable -path=pki pki
~~~

Bật secrets engine **chưa đủ** để cấp chứng thư; phải thiết lập CA/issuer và đường dẫn cấp phát hợp lệ trước khi gọi API issue.

Quản trị viên có thể tạo role demo như sau:

~~~bash
vault write pki/roles/server-int \
  allowed_domains="example.internal" \
  allow_subdomains=true \
  allow_bare_domains=false \
  allow_ip_sans=false \
  ttl="24h" \
  max_ttl="72h"
~~~

Ý nghĩa của policy cấp phát:

- **allowed_domains="example.internal"** cùng **allow_subdomains=true** cho phép các tên con phù hợp, chẳng hạn **api.example.internal** và **api-alt.example.internal**.
- **allow_bare_domains=false** không cho yêu cầu chính tên gốc **example.internal**.
- **allow_ip_sans=false** chặn việc thêm IP SAN tùy ý trong ví dụ.
- **ttl=24h** là thời hạn mặc định của role nếu yêu cầu không nêu TTL.
- **max_ttl=72h** giới hạn thời hạn mà role chấp nhận; yêu cầu **12h** nằm trong giới hạn đó.

Role chỉ là một phần của chính sách: issuer phải hợp lệ và còn thời hạn phù hợp, còn ứng dụng cần được cấp quyền gọi đúng endpoint.

Ví dụ policy HCL dành riêng cho workload có quyền phát hành chứng thư qua role **server-int**:

~~~hcl
path "pki/issue/server-int" {
  capabilities = ["update"]
}
~~~

Quản trị viên gắn policy này với phương thức xác thực workload (ví dụ Kubernetes auth hoặc AppRole) đã thiết lập. Ứng dụng chỉ cần quyền **update** đối với endpoint cấp phát của role cần sử dụng; không cần quyền tạo CA, chỉnh role, đọc private key CA hay cấp token quản trị.

**Không sử dụng root token trong ứng dụng.** Cũng không bật tùy chọn cho cấp mọi tên miền để xử lý nhanh lỗi cấu hình, vì điều đó phá vỡ giới hạn danh tính của role.

## 4. Thử yêu cầu bằng Vault CLI

Trước khi viết Java, quản trị viên hoặc workload thử nghiệm có thể gọi cùng endpoint bằng Vault CLI:

~~~bash
vault write -format=json pki/issue/server-int \
  common_name="api.example.internal" \
  alt_names="api.example.internal,api-alt.example.internal" \
  ttl="12h" \
  | jq '{
      serial_number: .data.serial_number,
      certificate_present: (.data.certificate != null),
      private_key_present: (.data.private_key != null),
      ca_chain_length: (.data.ca_chain | length)
    }'
~~~

Lệnh trên chỉ hiển thị thông tin không nhạy cảm, **không in private key**. Tham số **alt_names** là chuỗi các DNS/email SAN phân tách bằng dấu phẩy trong API của Vault; với **ip_sans** và **uri_sans** phải dùng trường riêng.

Để kiểm tra CN, SAN và thời hạn trên chứng thư vừa cấp:

~~~bash
vault write -format=json pki/issue/server-int \
  common_name="api.example.internal" \
  alt_names="api.example.internal,api-alt.example.internal" \
  ttl="12h" \
  | jq -r '.data.certificate' \
  | openssl x509 -noout -subject -dates -ext subjectAltName
~~~

Ví dụ dạng thông tin có thể quan sát được (giờ cụ thể thay đổi theo lúc yêu cầu):

~~~text
subject=CN = api.example.internal
notBefore=...
notAfter=...
X509v3 Subject Alternative Name:
    DNS:api.example.internal, DNS:api-alt.example.internal
~~~

Hai lệnh CLI **phát hành hai chứng thư khác nhau**, vì mỗi lần gọi endpoint issue là một yêu cầu cấp phát mới. Trong ứng dụng thật, cần quản lý vòng đời và lưu bản phát hành tương ứng một cách an toàn. Không lặp lại yêu cầu cấp chỉ để xem lại trường dữ liệu có thể lưu/kiểm tra từ lần cấp trước.

**Lưu ý bảo mật:** endpoint **issue** trả về **private_key** dưới dạng nội dung nhạy cảm đi cùng chứng thư; không ghi toàn bộ JSON vào console, log, crash report hoặc file nằm trong Git. Chứng thư công khai có thể được quan sát, nhưng private key phải được bảo vệ như một bí mật.

## 5. Gửi CN, SAN và TTL từ Java bằng Spring Vault

Ứng dụng Spring cần dependency **org.springframework.vault:spring-vault-core** (trực tiếp hoặc thông qua cấu hình dependency tương ứng) và một bean **VaultOperations** đã có endpoint Vault, TLS trust và xác thực workload. Trong Spring Cloud Vault, dùng cơ chế cấu hình và đăng nhập đang áp dụng của dự án để cung cấp bean này.

Spring Vault có hai thành phần cốt lõi:

- **VaultOperations.opsForPki("pki")** tạo API truy cập PKI tại mount **pki**. Nếu dùng mount mặc định, có thể gọi **opsForPki()**.
- **VaultCertificateRequest** biểu diễn yêu cầu gồm **commonName**, **altNames** và **ttl**, sau đó **VaultPkiOperations.issueCertificate(roleName, request)** gửi yêu cầu và nhận **VaultCertificateResponse**.

Ví dụ service:

~~~java
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultPkiOperations;
import org.springframework.vault.support.CertificateBundle;
import org.springframework.vault.support.VaultCertificateRequest;
import org.springframework.vault.support.VaultCertificateResponse;

@Service
public class ServiceCertificateIssuer {

    private static final String ROLE = "server-int";
    private static final String COMMON_NAME = "api.example.internal";

    private final VaultPkiOperations pki;

    public ServiceCertificateIssuer(VaultOperations vaultOperations) {
        this.pki = vaultOperations.opsForPki("pki");
    }

    public CertificateBundle issue() throws CertificateException {
        VaultCertificateRequest request = VaultCertificateRequest.builder()
                .commonName(COMMON_NAME)
                .altNames(List.of(
                        COMMON_NAME,
                        "api-alt.example.internal"))
                .ttl(Duration.ofHours(12))
                .build();

        VaultCertificateResponse response =
                pki.issueCertificate(ROLE, request);

        // getRequiredData() báo lỗi nếu response không chứa bundle.
        CertificateBundle bundle = response.getRequiredData();

        // Xác minh chứng thư hiện nằm trong khoảng thời gian có hiệu lực.
        X509Certificate x509 = bundle.getX509Certificate();
        x509.checkValidity();

        // Chỉ trả cho thành phần nội bộ được phép cài đặt TLS certificate.
        return bundle;
    }
}
~~~

Ở ví dụ này:

1. **commonName(COMMON_NAME)** đặt CN mong muốn.
2. **altNames(...)** gửi danh sách DNS SAN. Khai báo rõ CN trong SAN để chủ động đáp ứng kiểm tra tên miền.
3. **ttl(Duration.ofHours(12))** gửi thời gian hiệu lực yêu cầu; đây không phải cam kết Vault chắc chắn cấp đúng 12 giờ trong mọi cấu hình.
4. **issueCertificate(...)** chỉ yêu cầu phát hành theo role; Vault có thể từ chối nếu CN/SAN/TTL vi phạm role hoặc issuer không khả dụng.
5. **getRequiredData()** lấy **CertificateBundle**, chứa chứng thư X.509, private key do endpoint issue trả về và thông tin CA/issuer đi kèm.

**Private key được sinh ở phía Vault cho request issue và trả về trong response.** Vì ứng dụng nhận private key dưới dạng rõ, cần vận chuyển qua TLS, hạn chế đối tượng tiếp cận và cài đặt vào keystore/TLS runtime an toàn. Không serialize toàn bộ **CertificateBundle** vào response REST công khai hay log đối tượng này.

### Đọc thông tin chứng thư để kiểm tra kết quả

Một đoạn mã dùng **X509Certificate** có thể đọc thời hạn và SAN trước khi đưa chứng thư vào TLS runtime:

~~~java
CertificateBundle bundle = certificateIssuer.issue();
X509Certificate certificate = bundle.getX509Certificate();

System.out.println("Subject: " + certificate.getSubjectX500Principal());
System.out.println("Valid from: " + certificate.getNotBefore());
System.out.println("Valid until: " + certificate.getNotAfter());
System.out.println("SAN: " + certificate.getSubjectAlternativeNames());

// Tuyệt đối không in: bundle.getPrivateKey()
~~~

Đoạn minh họa chỉ in metadata của chứng thư. Trong ứng dụng thật, log ở mức phù hợp hoặc thu thập metric về **notAfter**, tránh log SAN/CN nếu đây là metadata nhạy cảm của hệ thống nội bộ.

Bạn có thể dùng **bundle.getCertificate()** để lấy chứng thư ở dạng đã mã hóa PEM/DER, **bundle.getPrivateKey()** để lấy private key (nhạy cảm), và **bundle.getIssuingCaCertificate()** để lấy chứng thư CA phát hành. Chúng không phải chuỗi có thể thay thế cho nhau: chứng thư công khai được gửi cho peer khi bắt tay TLS; private key phải được giữ bí mật ở phía máy chủ; CA chain cần được peer tin cậy đúng cách.

### Khi nào dùng sign thay vì issue?

Với **issueCertificate(...)**, Vault sinh cặp khóa và trả private key kèm chứng thư. Nếu yêu cầu **private key không rời khỏi máy/HSM tạo khóa**, ứng dụng cần tự sinh khóa và tạo **CSR**, rồi dùng **VaultPkiOperations.signCertificateRequest(...)** để Vault ký CSR. Khi đó Vault không cần nhận private key. Đây là khác biệt quan trọng khi chọn luồng PKI cho workload.

## 6. Những giới hạn TTL phải xác minh

Không nên giả định chứng thư có **notAfter = thời điểm Java gọi API + đúng 12h**. Điều cần kiểm tra là khoảng hiệu lực X.509 thực tế.

| Nguồn giới hạn | Tác động |
| --- | --- |
| **TTL yêu cầu (12h)** | Thời lượng mong muốn khi gọi issue. |
| **Role ttl (24h)** | TTL mặc định nếu ứng dụng không chỉ định giá trị. |
| **Role max_ttl (72h)** | Chặn yêu cầu vượt quá giới hạn vai trò. |
| **PKI/system mount TTL** | Có thể tác động tới thời lượng hợp lệ theo cấu hình Vault. |
| **CA/issuer hết hạn** | Có thể làm Vault rút ngắn hoặc từ chối cấp chứng thư tùy phiên bản/cấu hình; chứng thư không được giả định còn hữu ích sau khi chuỗi CA hết hiệu lực. |

Ví dụ yêu cầu **96h** với role **max_ttl=72h** phải được xem là yêu cầu không hợp lệ theo giới hạn role; không xử lý bằng cách tăng max TTL chỉ để vượt qua lỗi. Nếu không truyền TTL, Vault áp dụng thời hạn mặc định theo chính sách role/engine.

Có thể kiểm tra bằng Java:

~~~java
X509Certificate certificate = bundle.getX509Certificate();

certificate.checkValidity(); // Xác nhận hiện tại nằm trong [notBefore, notAfter].
long secondsRemaining = Duration.between(
        java.time.Instant.now(),
        certificate.getNotAfter().toInstant()
).getSeconds();

if (secondsRemaining <= 0) {
    throw new IllegalStateException("Chứng thư không còn hiệu lực");
}
~~~

**Đừng dùng TTL của Vault token hoặc lease làm nguồn chuẩn cho ngày hết hạn X.509.** Theo dõi chính trường **notAfter** trong chứng thư và thiết kế luồng cấp lại trước khi hết hạn. Việc bật TTL 12 giờ không khiến ứng dụng tự động thay chứng thư đang phục vụ TLS; cơ chế tự gia hạn/cài đặt lại là phần cần xây dựng riêng.

## 7. Xác minh SAN đúng kiểu dữ liệu

Subject Alternative Name trong X.509 gồm nhiều kiểu. Trong Java, **X509Certificate.getSubjectAlternativeNames()** trả về các mục có type; **type 2** biểu diễn **DNS name**, **type 7** biểu diễn địa chỉ IP.

Ví dụ hàm kiểm tra một DNS SAN bắt buộc:

~~~java
import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;

public static boolean hasDnsSan(
        X509Certificate certificate, String expectedDnsName)
        throws CertificateParsingException {

    Collection<List<?>> names = certificate.getSubjectAlternativeNames();
    if (names == null) {
        return false;
    }

    return names.stream().anyMatch(entry ->
            Integer.valueOf(2).equals(entry.get(0))
            && expectedDnsName.equalsIgnoreCase(String.valueOf(entry.get(1))));
}
~~~

Ví dụ sử dụng sau khi issue:

~~~java
X509Certificate cert = certificateIssuer.issue().getX509Certificate();

if (!hasDnsSan(cert, "api.example.internal")
        || !hasDnsSan(cert, "api-alt.example.internal")) {
    throw new IllegalStateException("Chứng thư thiếu DNS SAN yêu cầu");
}
~~~

Hàm trên chỉ kiểm tra **sự hiện diện của DNS SAN được cấp**, không thay thế thuật toán xác minh hostname và toàn bộ TLS peer verification của JDK/HTTP client. Hostname wildcard, IDN, chuỗi CA, mục đích sử dụng khóa, tin cậy CA và revocation cần được xử lý bởi các thành phần TLS được cấu hình đúng chuẩn.

Nếu dịch vụ được truy cập bằng IP, phải yêu cầu **IP SAN** qua **ipSubjectAltNames(...)** và bảo đảm role có **allow_ip_sans=true** cùng ràng buộc đủ chặt. Không nhét địa chỉ IP vào **altNames(...)** với kỳ vọng nó trở thành IP SAN.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xác minh/xử lý |
| --- | --- | --- |
| HTTP 403 / permission denied | Token workload thiếu **update** ở **pki/issue/server-int**. | Kiểm tra policy, phương thức auth và path chính xác; không thử bằng root token trong ứng dụng. |
| Role báo name không hợp lệ | CN hoặc một SAN vượt **allowed_domains**, không được phép wildcard hoặc tên miền sai. | Kiểm tra từng CN/SAN so với role; chỉ yêu cầu danh tính thực sự cần. |
| TTL không được chấp nhận | TTL vượt **max_ttl** hoặc giới hạn PKI/issuer. | Điều chỉnh TTL trong giới hạn được quản trị cho phép, kiểm tra thời hạn CA. |
| Chứng thư thiếu tên kết nối | DNS hostname không xuất hiện trong SAN, hoặc đã loại CN khỏi SAN. | Đưa hostname kết nối vào DNS SAN và xác minh chứng thư thực tế. |
| Truy cập bằng IP bị lỗi | Role chặn IP SAN, hoặc chứng thư chỉ chứa DNS SAN. | Dùng DNS được quản lý hoặc cấu hình IP SAN hợp lệ theo policy. |
| Java không kết nối được tới Vault | DNS, TLS trust, token hết hạn, network hoặc Vault không sẵn sàng. | Kiểm tra kết nối qua TLS, health và xác thực workload; phân loại 4xx với lỗi hạ tầng. |
| Trình duyệt/TLS client không tin chứng thư | CA phát hành chưa nằm trong truststore hoặc chain thiếu/sai. | Cài đặt đúng CA trust chain phía client; không tắt certificate validation. |
| TLS vẫn dùng chứng thư cũ | Đã issue mới nhưng chưa nạp vào TLS runtime, hoặc chưa reload listener. | Thiết lập cơ chế thay keystore/SSL context an toàn và xác minh chứng thư đang được phục vụ. |

Khi gặp lỗi cấp phát, ghi **tên operation**, role, mã phản hồi, trace/correlation ID và thời điểm; tránh ghi request/response nguyên vẹn vì có thể chứa **private_key**, token hoặc thông tin hạ tầng nhạy cảm. Retry có giới hạn cho sự cố tạm thời; không retry liên tục cho yêu cầu sai tên miền hoặc thiếu quyền.

Một lần retry **issue** có thể tạo thêm chứng thư mới nếu yêu cầu trước thực ra đã hoàn thành nhưng client mất phản hồi. Cần dự phòng hiện tượng cấp phát lặp, theo dõi serial number và quản lý việc thu hồi chứng thư không còn dùng.

## 9. Thực hành kiểm thử tích hợp

Kiểm thử có ý nghĩa cần một Vault test đã bật PKI, CA/issuer hợp lệ, role **server-int** như cấu hình minh họa và workload có đúng quyền issue. Không nên chạy test cấp chứng thư tùy tiện trên PKI production vì mỗi lần chạy tạo một chứng thư mới.

Ví dụ với JUnit 5 và AssertJ trong ứng dụng Spring Boot đã cấu hình kết nối tới Vault test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.time.Instant;
import java.util.Collection;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.support.CertificateBundle;

@SpringBootTest
class ServiceCertificateIssuerIT {

    @Autowired
    ServiceCertificateIssuer certificateIssuer;

    @Test
    void issuesCertificateWithExpectedDnsSansAndUsefulLifetime() throws Exception {
        CertificateBundle bundle = certificateIssuer.issue();
        X509Certificate certificate = bundle.getX509Certificate();

        certificate.checkValidity();

        assertThat(hasDnsSan(certificate, "api.example.internal")).isTrue();
        assertThat(hasDnsSan(certificate, "api-alt.example.internal")).isTrue();
        assertThat(bundle.getSerialNumber()).isNotBlank();

        Instant now = Instant.now();
        Instant notAfter = certificate.getNotAfter().toInstant();
        assertThat(notAfter).isAfter(now);

        // Kiểm tra giới hạn rộng để tránh phụ thuộc vài giây trôi qua.
        assertThat(notAfter).isBefore(
                now.plus(Duration.ofHours(12).plusMinutes(10)));
    }

    private static boolean hasDnsSan(
            X509Certificate certificate, String expectedDnsName)
            throws CertificateParsingException {

        Collection<List<?>> names = certificate.getSubjectAlternativeNames();
        return names != null && names.stream().anyMatch(entry ->
                Integer.valueOf(2).equals(entry.get(0))
                && expectedDnsName.equalsIgnoreCase(String.valueOf(entry.get(1))));
    }
}
~~~

Hàm **hasDnsSan** trong test dùng cùng cách kiểm tra ở mục 7. Giới hạn thời gian phía trên là kỳ vọng cho cấu hình lab **12 giờ**, không phải tiêu chuẩn chung cho mọi Vault role. Nếu Vault/CA được cấu hình thời hạn ngắn hơn, phải điều chỉnh kỳ vọng theo chính sách thực tế.

Các trường hợp test bổ sung nên bao gồm: token không có quyền issue phải bị từ chối; yêu cầu tên miền nằm ngoài **example.internal** phải thất bại; yêu cầu TTL vượt **max_ttl** phải bị từ chối; chứng thư lấy được phải có chuỗi tin cậy phù hợp và có thể phục vụ một kết nối TLS thử nghiệm. Không đưa private key thật vào assertion message hoặc snapshot test.

## 10. Checklist vận hành

1. Xác định rõ **hostname thực sự được client kết nối**, đưa hostname đó vào **DNS SAN** và chỉ yêu cầu các SAN cần thiết.
2. Đảm bảo PKI role có **allowed_domains**, giới hạn SAN, **ttl** và **max_ttl** theo chính sách của tổ chức; workload chỉ có quyền **pki/issue/<role>** cần thiết.
3. Trong Java, tạo **VaultCertificateRequest** với **commonName**, **altNames**, **ttl**, rồi gọi **VaultOperations.opsForPki(...).issueCertificate(...)**.
4. Xác minh chứng thư X.509 thực tế: **notBefore**, **notAfter**, DNS SAN và chuỗi CA; chỉ cài private key ở nơi được phép.
5. Theo dõi hạn dùng **notAfter**, cấp lại và cập nhật TLS listener trước hạn, có quan sát lỗi/độ trễ và chiến lược khôi phục.
6. Tách riêng luồng **issue** (Vault sinh và trả private key) và **sign CSR** (ứng dụng giữ private key của mình) theo yêu cầu bảo mật.

Khi hoàn thành bài thực hành, ứng dụng Java đã có thể **yêu cầu chứng thư PKI đúng tên miền, SAN và TTL** bằng Spring Vault, đồng thời kiểm chứng các thuộc tính thực cấp và thực thi ranh giới phân quyền mà HashiCorp Vault đặt ra.

### Tài liệu tham khảo chính thức

- [Spring Vault — VaultPkiOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultPkiOperations.html).
- [Spring Vault — VaultCertificateRequest API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultCertificateRequest.html).
- [HashiCorp Vault — PKI Secrets Engine HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/pki).
