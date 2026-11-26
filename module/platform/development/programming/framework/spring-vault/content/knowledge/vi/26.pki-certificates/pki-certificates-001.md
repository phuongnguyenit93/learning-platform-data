# PKI secrets engine, CA và role cấp chứng thư

## 1. Vì sao ứng dụng Java cần Vault PKI?

Khi hai dịch vụ Java dùng HTTPS hoặc mutual TLS (mTLS), mỗi bên cần chứng thư X.509 và phải xác minh danh tính của peer. Nếu chứng thư được cấp thủ công, việc chờ ký CSR, gửi file và theo dõi ngày hết hạn dễ gây gián đoạn hoặc lộ khóa.

**HashiCorp Vault PKI secrets engine** hoạt động như một Certificate Authority (CA), tự động ký chứng thư theo quy tắc xác định trước. **Spring Vault** cho ứng dụng Java gọi API PKI thông qua `VaultTemplate`/`VaultOperations` và `VaultPkiOperations`. Ứng dụng xác thực với Vault bằng danh tính workload (Kubernetes auth, AppRole hoặc cơ chế phù hợp), rồi Vault dùng ACL policy để kiểm soát quyền gọi endpoint.

Một lần cấp chứng thư thành công phải đồng thời thỏa **ba lớp**:

1. **PKI secrets engine và CA:** engine được mount ở đường dẫn xác định, có issuer CA hoạt động.
2. **PKI role:** định nghĩa tên DNS/SAN, loại chứng thư, mục đích sử dụng và thời hạn được phép.
3. **Vault authentication và ACL policy:** token của workload có quyền gọi endpoint cấp chứng thư cho role đó.

Mục tiêu bài học: thiết lập Root CA → Intermediate CA trong lab, tạo role cấp chứng thư cho dịch vụ, gọi API từ Spring Vault, phân biệt cấp chứng thư với ký CSR và vận hành vòng đời thay thế/thu hồi chứng thư.

> **Giới hạn môi trường:** Các lệnh tạo root CA dưới đây chỉ áp dụng cho Vault test độc lập. Trong production, nên giữ root CA được cách ly/offline hoặc do giải pháp CA/HSM của tổ chức quản lý. Không thực hành trên CA đang phục vụ hệ thống thật.

## 2. Root CA, Intermediate CA, issuer và leaf certificate

~~~text
Root CA (trust anchor; public certificate nằm trong truststore)
│  Khóa riêng root được bảo vệ nghiêm ngặt
└── KÝ chứng thư Intermediate CA
    │  Khóa riêng intermediate do Vault PKI quản lý
    ├── KÝ TLS certificate cho api.svc.example.test
    ├── KÝ TLS certificate cho worker.svc.example.test
    └── KÝ các certificate khác được role cho phép
~~~

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Root CA** | Certificate authority gốc, là trust anchor của hệ thống xác minh. | `Example Test Root CA`. |
| **Intermediate CA** | CA trung gian có chứng thư do root ký, thường trực tiếp ký leaf. | `Example Test Intermediate CA`. |
| **Issuer** | Một CA cụ thể trong PKI mount; mount có thể có nhiều issuer. | Default issuer trong `pki_int/`. |
| **Leaf certificate** | Chứng thư dành cho service; chứa public key, danh tính/SAN, thời hạn, chữ ký CA. | `api.svc.example.test`. |
| **Private key của leaf** | Dùng chứng minh service sở hữu danh tính TLS. | Nằm trong keystore/HSM/bộ nhớ ứng dụng. |
| **Certificate chain** | Chuỗi leaf → intermediate → root dùng khi xác minh tin cậy. | Server gửi leaf và intermediate; client tin root. |
| **PKI role** | Tập luật cấp chứng thư (DNS/SAN, TTL, issuer, key type, usage). | `service-tls`. |

TLS sẽ từ chối chứng thư ngay cả khi chứng thư đó thật sự được Vault ký, nếu peer **không tin root CA**, thiếu intermediate CA, tên trong SAN không trùng với endpoint, chứng thư hết hạn, sai mục đích sử dụng hoặc vi phạm quy tắc xác minh trạng thái thu hồi.

**Root CA và intermediate CA là vai trò của chứng thư/issuer**, không phải tên mount. PKI engine type đều là `pki`, dù mount đặt tên `pki_root` hay `pki_int`. Đối với môi trường sản xuất, dùng intermediate để cấp chứng thư dịch vụ giúp giảm tần suất sử dụng root private key và đơn giản hóa thay thế một phạm vi CA.

## 3. Phân biệt mount path, role, issuer và ACL

Giả sử Vault có PKI secrets engine tại `pki_int/`, role `service-tls` và workload `orders-app`:

| Khái niệm | Giá trị mẫu | Trách nhiệm |
| --- | --- | --- |
| Secrets engine type | `pki` | Cung cấp các API PKI và chứng thư X.509. |
| Mount path | `pki_int` | Định vị instance PKI trong URL Vault. |
| Issuer | Default issuer | CA dùng ký certificate, có thể được role chỉ định. |
| PKI role | `service-tls` | Quy định certificate nào được phép cấp. |
| Vault auth role | `orders-app` | Cấp danh tính và token cho workload theo auth method. |
| ACL policy | `orders-cert-issue` | Giới hạn endpoint mà token được phép gọi. |

Lời gọi HTTP `POST /v1/pki_int/issue/service-tls` có nghĩa là dùng PKI mount `pki_int`, yêu cầu Vault **tạo khóa riêng leaf và phát hành chứng thư** dựa theo role `service-tls`. Để gọi API thành công, workload cần token có capability `update` trên `pki_int/issue/service-tls`; certificate request vẫn phải hợp lệ theo các ràng buộc của PKI role.

**PKI role không phải auth role hoặc ACL policy.** Định nghĩa `allowed_domains` trong role không tự động cấp quyền truy cập API; gắn policy cho token cũng không làm role cho phép phát hành mọi tên miền.

## 4. Thực hành thiết lập CA trong Vault test

Ví dụ dùng Vault CLI đã xác thực bằng token quản trị lab. Các lệnh tương thích shell Bash; các file CSR/PEM tạo trong lab phải nằm ở nơi kiểm soát quyền truy cập. Tên miền `example.test` là tên dành cho thử nghiệm, không phải DNS production.

### 4.1. Tạo Root CA test

~~~bash
vault secrets enable -path=pki_root pki
vault secrets tune -max-lease-ttl=87600h pki_root

# Chỉ dành cho lab: root private key được tạo và lưu nội bộ tại Vault.
vault write -field=certificate pki_root/root/generate/internal \
  common_name="Example Test Root CA" \
  issuer_name="example-test-root" \
  ttl=87600h > root_ca.pem
~~~

`pki_root/root/generate/internal` tạo root tự ký. Tùy chọn `internal` giữ private key của CA ở Vault. Root public certificate dùng để thiết lập truststore trong môi trường test. Không chạy lại lệnh tạo root trên CA đã được ứng dụng tin cậy: thay trust anchor sẽ yêu cầu cập nhật truststore và chuỗi tin cậy ở các bên tham gia.

### 4.2. Tạo Intermediate CA và xin root ký

~~~bash
vault secrets enable -path=pki_int pki
vault secrets tune -max-lease-ttl=43800h pki_int

# Vault tự tạo private key intermediate và trả CSR.
vault write -field=csr pki_int/intermediate/generate/internal \
  common_name="Example Test Intermediate CA" \
  ttl=43800h > intermediate.csr

# Root CA ký CSR của intermediate.
vault write -field=certificate pki_root/root/sign-intermediate \
  csr=@intermediate.csr \
  format=pem_bundle \
  ttl=43800h > signed_intermediate.pem

# Gắn chứng thư đã được ký trở lại intermediate mount.
vault write pki_int/intermediate/set-signed \
  certificate=@signed_intermediate.pem
~~~

Có ba hành động khác nhau: tạo private key/CSR intermediate, ký CSR bằng root, và cài chứng thư đã ký. Private key intermediate không cần rời khỏi Vault. Trong production có thể giữ root hoàn toàn bên ngoài Vault và chỉ chuyển CSR/chứng thư CA được ký theo quy trình phê duyệt.

Vault hỗ trợ nhiều issuer trong cùng một PKI mount; khi vận hành nhiều issuer phải kiểm soát cấu hình default issuer và role, tránh để workload tùy ý chọn sai CA bằng endpoint cho phép override issuer. Không mặc định mọi certificate trong cùng mount đều được ký bằng một issuer nếu cấu hình đã thay đổi.

### 4.3. URL để client truy xuất CA và trạng thái thu hồi

~~~bash
# Tên pki.example.test phải được thay bằng endpoint phù hợp môi trường.
vault write pki_int/config/urls \
  issuing_certificates="https://pki.example.test/v1/pki_int/ca" \
  crl_distribution_points="https://pki.example.test/v1/pki_int/crl"
~~~

Các URL này dùng cho extension AIA/CRL Distribution Points của chứng thư. Phía xác minh phải truy cập được URL tương ứng nếu dùng cách phân phối đó; đối với client ở máy khác, URL `localhost` thường sai. Tùy phiên bản Vault và thiết kế nhiều issuer, có thể cần cấu hình endpoint issuer-specific, CRL hoặc OCSP; cần thử hành vi thực tế của client.

## 5. PKI role quy định chứng thư được cấp

Tạo role chỉ cấp chứng thư cho các service dưới tên miền `svc.example.test`:

~~~bash
vault write pki_int/roles/service-tls \
  allowed_domains="svc.example.test" \
  allow_subdomains=true \
  allow_bare_domains=false \
  allow_wildcard_certificates=false \
  ttl="12h" \
  max_ttl="24h" \
  server_flag=true \
  client_flag=false
~~~

| Field | Ý nghĩa |
| --- | --- |
| `allowed_domains` | Giới hạn danh sách tên miền được phép yêu cầu. |
| `allow_subdomains` | Cho phép cấp chứng thư cho tên con như `api.svc.example.test`. |
| `allow_bare_domains` | Có cho cấp chứng thư đúng tên `svc.example.test` hay không. |
| `allow_wildcard_certificates` | Có cho cấp chứng thư `*.svc.example.test` hay không. |
| `ttl` | Thời gian hiệu lực mặc định nếu request không chỉ rõ. |
| `max_ttl` | TTL tối đa do role quy định; còn phụ thuộc mount/CA. |
| `server_flag`, `client_flag` | Xác định mục đích sử dụng TLS server/client theo Extended Key Usage. |

Trong ví dụ, `api.svc.example.test` có thể hợp lệ, còn `admin.example.org` phải bị từ chối. Role chỉ phát hành cho TLS server; nếu sử dụng **mTLS**, thiết kế role cấp chứng thư client riêng với `client_flag` phù hợp. Đặt role theo ranh giới workload/miền DNS và quyền sử dụng. Tránh bật `allow_any_name=true` cho các ứng dụng thông thường hoặc cho phép wildcard khi không có yêu cầu rõ ràng.

Kiểm tra và yêu cầu cấp chứng thư từ Vault CLI:

~~~bash
vault read pki_int/roles/service-tls

vault write pki_int/issue/service-tls \
  common_name="api.svc.example.test" \
  ttl="6h"
~~~

Khi gọi endpoint `issue`, Vault thường trả các trường `certificate`, `private_key`, `issuing_ca`, `ca_chain`, `serial_number` và `expiration`. **Private key của leaf được Vault sinh ra rồi gửi về ứng dụng**; vì vậy không ghi kết quả issue chứa private key vào log, chat, CI artifact hoặc hệ thống nhật ký không được bảo vệ.

Thử request vượt role trong lab:

~~~bash
vault write pki_int/issue/service-tls \
  common_name="admin.example.org" \
  ttl="6h"
# Kỳ vọng: Vault từ chối tên miền ngoài phạm vi role.
~~~

Ngoài DNS SAN, các role cũng có thể hạn chế IP SAN, URI SAN, key type, key size, wildcard và issuer. Luôn gắn ràng buộc theo danh tính workload thực sự, tránh làm một role cấp được mọi danh tính cho mọi service.

## 6. Policy gắn với endpoint, không phải với tên CA

Cho workload runtime quyền **chỉ yêu cầu certificate** theo role:

~~~hcl
# orders-cert-issue.hcl
path "pki_int/issue/service-tls" {
  capabilities = ["update"]
}
~~~

Nếu workload tự sinh private key và gửi CSR để Vault ký, cấp quyền trên endpoint `sign` theo đúng role:

~~~hcl
path "pki_int/sign/service-tls" {
  capabilities = ["update"]
}
~~~

Capability `update` cho phép gọi endpoint cấp chứng thư tương ứng. Quyền này phải được cấp qua token của workload sau khi xác thực, ví dụ auth role Kubernetes/AppRole theo cách tổ chức triển khai. Token của Java runtime **không cần** quyền chỉnh sửa `pki_int/roles/...`, tạo root CA, ký intermediate hoặc đổi issuer.

Các tác vụ quản trị như `pki_int/root/...`, `pki_int/intermediate/...`, `pki_int/issuers/...`, `pki_int/roles/...` và `pki_int/revoke` cần quyền riêng. Các endpoint như `sign-verbatim` không giới hạn chứng thư như role thông thường có mức rủi ro cao và không được cấp cho ứng dụng thường ngày.

**Nguyên tắc:** policy giới hạn *ai được gọi endpoint*; role giới hạn *chứng thư nào có thể được phát hành*. Với yêu cầu server-only, chỉ cấp quyền issue cho role server đúng miền; không cấp wildcard quyền ở toàn bộ mount vì tiện.

## 7. Gọi PKI từ Spring Vault

`VaultOperations` cung cấp hai cách lấy `VaultPkiOperations`:

~~~java
VaultPkiOperations defaultPki = vaultOperations.opsForPki();
// Dùng mount mặc định: pki/

VaultPkiOperations intermediate = vaultOperations.opsForPki("pki_int");
// Dùng mount: pki_int/
~~~

Tham số `"pki_int"` là **mount path**. Không truyền tên role `service-tls` hay endpoint `/v1/pki_int/issue/service-tls` vào `opsForPki(path)`. Role name truyền riêng khi gọi `issueCertificate` hoặc `signCertificateRequest`.

Ví dụ ứng dụng Spring đã khởi tạo bean `VaultOperations` với TLS, xác thực workload và policy như mục trước:

~~~yaml
app:
  pki:
    mount: pki_int
    role: service-tls
~~~

~~~java
import java.security.KeyStore;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultPkiOperations;
import org.springframework.vault.support.CertificateBundle;
import org.springframework.vault.support.VaultCertificateRequest;
import org.springframework.vault.support.VaultCertificateResponse;

@Service
public class ServiceCertificateIssuer {

    private final VaultPkiOperations pki;
    private final String roleName;

    public ServiceCertificateIssuer(
            VaultOperations vaultOperations,
            @Value("${app.pki.mount}") String mount,
            @Value("${app.pki.role}") String roleName) {
        this.pki = vaultOperations.opsForPki(mount);
        this.roleName = roleName;
    }

    public CertificateBundle issueServerCertificate(String dnsName) {
        VaultCertificateRequest request = VaultCertificateRequest.builder()
                .commonName(dnsName)
                .ttl(Duration.ofHours(6))
                .build();

        VaultCertificateResponse response =
                pki.issueCertificate(roleName, request);
        return response.getRequiredData();
    }

    public KeyStore createInMemoryKeyStore(String dnsName) {
        CertificateBundle bundle = issueServerCertificate(dnsName);
        return bundle.createKeyStore("service-key");
    }
}
~~~

`VaultCertificateRequest` hỗ trợ các thuộc tính như `commonName`, `ttl`, `altNames`, `withIpSubjectAltName`. Vault kiểm tra chúng theo role. `CertificateBundle` chứa certificate, serial number, CA certificate/chain và private key do Vault cấp, đồng thời có thể tạo `KeyStore` cho Java.

Tạo `KeyStore` **chưa tự động cài chứng thư** vào HTTPS server/HTTP client. Ứng dụng phải cung cấp `KeyManager`/SSL context phù hợp cho TLS stack (ví dụ embedded web server, HTTP client, gRPC). Nhiều TLS stack chỉ đọc keystore khi khởi động, vì vậy cần kiểm thử restart hoặc hot reload khi thay certificate. Hạn chế ghi private key ra filesystem, không hiển thị private key trong exception, log hay endpoint chẩn đoán.

### 7.1. Issue khác gì sign CSR?

| Phương thức | Endpoint | Nơi tạo private key leaf | Vault trả về |
| --- | --- | --- | --- |
| `issueCertificate` | `pki_int/issue/service-tls` | Vault sinh key và trả về cho caller. | Certificate, private key, chain, serial, thời hạn. |
| `signCertificateRequest` | `pki_int/sign/service-tls` | Workload/agent tạo private key tại nơi quản lý khóa, gửi CSR lên Vault. | Chứng thư đã ký và thông tin CA, **không có private key leaf**. |

Ví dụ Java khi ứng dụng đã có CSR PEM (và đã giữ private key tương ứng ở nơi an toàn):

~~~java
import org.springframework.vault.support.VaultSignCertificateRequestResponse;

VaultCertificateRequest request =
        VaultCertificateRequest.builder()
                .commonName("api.svc.example.test")
                .ttl(Duration.ofHours(6))
                .build();

VaultSignCertificateRequestResponse signed =
        intermediate.signCertificateRequest("service-tls", csrPem, request);
~~~

Đoạn này giả định `intermediate` là `VaultPkiOperations` cho mount `pki_int` và `csrPem` chứa CSR hợp lệ. Việc gửi CSR không tự chứng minh service được quyền nhận danh tính trong CSR: Vault auth, ACL, role và quy tắc SAN vẫn phải kiểm soát việc ký. Luồng `sign` phù hợp khi cần private key không rời khỏi keystore/HSM hoặc Vault Agent của workload.

## 8. Chứng thư hết hạn, cấp lại, thu hồi và trust chain

Certificate X.509 có `NotBefore` và `NotAfter`. **Chứng thư đã ký không kéo dài ngày hết hạn bằng cách renew token Vault.** Để duy trì TLS, cấp mới certificate trước khi bản cũ hết hạn, cập nhật key/certificate chain tại service và xác minh kết nối.

~~~text
Workload login Vault → token có quyền pki_int/issue/service-tls
    ↓
Yêu cầu leaf certificate (hoặc ký CSR)
    ↓
Nhận certificate + chain (+ private key khi dùng issue)
    ↓
Nạp vào TLS key manager / keystore, peer tin root CA
    ↓
Giám sát NotAfter, cấp mới trước khi hết hạn
    ↓
Reload SSL context / restart an toàn, kiểm tra handshake
    ↓
Thu hồi serial cũ khi cần và kiểm tra phân phối trạng thái
~~~

Cần phân biệt các loại thời hạn:

- **Vault token TTL:** còn quyền gọi Vault hay không; xác thực workload cần có cơ chế refresh/renew token tương ứng.
- **Certificate lifetime:** chứng thư X.509 hợp lệ tới `NotAfter`; phải cấp lại và nạp lại certificate.
- **Vault lease:** response PKI có thể có lease theo cấu hình (ví dụ `generate_lease`), nhưng renew lease không trực tiếp đổi ngày hết hạn trong X.509 certificate đã ký.
- **CA/issuer lifetime:** nếu issuer hết hạn hoặc thay CA, peer phải có trust chain thích hợp và role/issuer cần được cập nhật theo kế hoạch.

Có thể dùng Vault Agent, cert-manager, sidecar hay scheduler của ứng dụng cho việc cấp lại. Spring Vault hỗ trợ gọi API; việc tự động nạp lại certificate vào TLS endpoint phụ thuộc giải pháp tích hợp. Đặt thời gian thay sớm để chừa dư địa cho gián đoạn Vault, retry và triển khai nhiều replica. Giám sát certificate hiện *đang được server trình bày*, tránh chỉ kiểm tra certificate vừa lấy mà chưa dùng.

### 8.1. Thu hồi chứng thư

Khi private key bị lộ hoặc dịch vụ bị thu hồi quyền, vai trò vận hành có thể gọi:

~~~bash
vault write pki_int/revoke \
  serial_number="SERIAL_NUMBER_RETURNED_BY_VAULT"
~~~

Từ Spring Vault, `VaultPkiOperations.revoke(serialNumber)` thực hiện thao tác tương ứng và yêu cầu quyền Vault phù hợp:

~~~java
// Chỉ sử dụng bằng identity có quyền revoke riêng.
pki.revoke(serialNumber);
~~~

**Thu hồi không đồng nghĩa mọi peer từ chối chứng thư ngay lập tức.** Peer phải thực sự kiểm tra CRL/OCSP theo cấu hình, có thể chịu cache hoặc độ trễ cập nhật. Với cert TTL ngắn, một số kiến trúc ưu tiên cấp mới thường xuyên, nhưng vẫn phải quản lý rủi ro khi private key đã bị chiếm dụng.

## 9. Lỗi phổ biến khi triển khai

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| HTTP 403 `permission denied` | Token thiếu `update` trên `pki_int/issue/service-tls`; identity/namespace không đúng. | Kiểm tra auth role, policy của token và endpoint thật. |
| HTTP 404 / không có endpoint | Sai mount `opsForPki(path)`, PKI chưa được bật, role chưa tồn tại. | Chạy `vault secrets list` và `vault read pki_int/roles/service-tls` bằng identity kiểm tra phù hợp. |
| Lỗi CN/SAN không được phép | Request nằm ngoài `allowed_domains` hoặc vi phạm wildcard, URI/IP SAN rule. | Đối chiếu request với cấu hình role; thêm ràng buộc đúng nhu cầu. |
| Lỗi TTL | TTL yêu cầu vượt `max_ttl` của role/mount hoặc hiệu lực CA không đủ. | So sánh TTL request, role, mount và `NotAfter` của issuer. |
| Java `PKIX path building failed` | Truststore không có CA tin cậy hoặc certificate chain thiếu/sai. | Kiểm tra CA root được cài, intermediate chain và truststore mà JVM thực sự sử dụng. |
| `No subject alternative DNS name matching` | Certificate không có DNS SAN trùng hostname kết nối. | Kiểm tra DNS SAN/SNI và endpoint đang truy cập. |
| TLS handshake thất bại dù chain hợp lệ | Sai client/server EKU, private key không khớp certificate, TLS stack chưa reload. | Kiểm tra key pair, role flags, SSL context và certificate hiện được trình bày. |
| Revoked certificate vẫn kết nối được | Client không kiểm tra trạng thái thu hồi hoặc CRL/OCSP cache. | Kiểm tra URL distribution, khả năng truy cập và chính sách revocation của peer. |

Mã HTTP không đủ để kết luận một lỗi; phải xét mount, role, policy, namespace, trạng thái issuer và lỗi TLS. Ghi log loại thao tác, mã lỗi, latency, thời gian đến hạn và correlation ID; **không ghi private key, certificate bundle đầy đủ, Vault token hay CSR chứa thông tin không cần công bố**.

## 10. Thực hành kiểm thử tích hợp

Thực hiện trên Vault test độc lập, không dùng token production:

1. Tạo `pki_root` và `pki_int`, ký và cài intermediate CA; xác minh chain tới root.
2. Tạo role `service-tls` theo đúng miền `svc.example.test` và TTL ≤ 24 giờ.
3. Gán policy `update` trên `pki_int/issue/service-tls` cho workload test.
4. Gọi `vaultOperations.opsForPki("pki_int")` và `issueCertificate` từ Java với `api.svc.example.test`, TTL 6 giờ.
5. Kiểm tra bundle có certificate, issuing CA, serial number, private key và ngày hết hạn; xác minh leaf certificate có SAN phù hợp.
6. Nạp certificate/chain vào TLS server test và root CA vào truststore của client; kiểm tra HTTPS hoặc mTLS handshake thật.
7. Thử cấp cho `admin.example.org` hoặc tên wildcard bị cấm; kỳ vọng bị Vault từ chối.
8. Dùng token test không có quyền issue; kiểm tra lỗi 403 được xử lý an toàn; cấu hình sai mount để kiểm tra lỗi đường dẫn.
9. Cấp lại certificate, cập nhật SSL context/restart endpoint và kiểm tra certificate mới được trình bày, tránh gián đoạn kết nối.
10. Thu hồi một serial bằng token quản trị test, quan sát cơ chế CRL/OCSP theo thiết kế và xác minh log không chứa private key.

Ví dụ assertion sau khi gọi Vault test:

~~~java
CertificateBundle bundle =
        issuer.issueServerCertificate("api.svc.example.test");

assertNotNull(bundle.getX509Certificate());
assertNotNull(bundle.getX509IssuerCertificate());
assertNotNull(bundle.getPrivateKeySpec());
assertNotNull(bundle.getSerialNumber());

bundle.getX509Certificate().checkValidity();
~~~

`checkValidity()` chỉ xác minh thời gian hiệu lực hiện tại; nó **chưa** kiểm tra SAN/hostname, chain, chữ ký CA hay trạng thái thu hồi. Integration test cần có kiểm tra PKIX validation và TLS handshake thật. Mock `VaultPkiOperations` chỉ kiểm tra logic gọi API, không chứng minh mount/role/ACL trên Vault đã cấu hình đúng.

## 11. Câu hỏi tự đánh giá

1. Vì sao production thường dùng intermediate CA cấp leaf certificate thay vì ký bằng root CA?
2. `pki_int`, `service-tls`, issuer và auth role khác nhau ở bước nào?
3. Vì sao policy `update` trên endpoint `issue` vẫn không cho cấp certificate mang tên `admin.example.org`?
4. So sánh `issueCertificate` và `signCertificateRequest` theo nơi tạo và lưu private key.
5. Khi Java báo `PKIX path building failed` dù Vault đã ký, cần kiểm tra những gì?
6. Token Vault được renew có làm certificate X.509 tự kéo dài `NotAfter` không?
7. Làm thế nào bảo đảm service thực sự trình bày certificate mới sau khi được cấp lại?
8. Vì sao việc revoke một serial chưa chắc khiến mọi TLS client từ chối nó ngay?

## Tài liệu tham khảo

- [Spring Vault — Vault Secrets Engines, phần PKI](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Vault — VaultPkiOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultPkiOperations.html)
- [Spring Vault — VaultCertificateRequest API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultCertificateRequest.html)
- [HashiCorp Vault — PKI secrets engine](https://developer.hashicorp.com/vault/docs/secrets/pki)
- [HashiCorp Vault — Root CA quick start](https://developer.hashicorp.com/vault/docs/secrets/pki/quick-start-root-ca)
- [HashiCorp Vault — Intermediate CA quick start](https://developer.hashicorp.com/vault/docs/secrets/pki/quick-start-intermediate-ca)
- [HashiCorp Vault — PKI HTTP API, role và issue/sign](https://developer.hashicorp.com/vault/api-docs/secret/pki)
- [HashiCorp Vault — PKI security considerations](https://developer.hashicorp.com/vault/docs/secrets/pki/considerations)
