# Cấp chứng thư thử nghiệm rồi thay thế khi sắp hết hạn

## 1. Mục tiêu của bài thực hành tổng hợp

Trong module **SPRING_VAULT**, ứng dụng Java đã biết truy cập HashiCorp Vault qua `VaultTemplate`/`VaultOperations`, đăng nhập theo danh tính workload và dùng Vault ACL để giới hạn quyền. Bài này ghép các kỹ năng đó vào một kịch bản cụ thể: **ứng dụng nhận chứng thư TLS từ Vault PKI, xác minh chứng thư, theo dõi thời gian hết hạn và cấp chứng thư mới đủ sớm để thay thế chứng thư đang phục vụ**.

Giả sử một dịch vụ thử nghiệm tên `orders-api` đang phục vụ HTTPS ở tên miền `orders.lab.example.test`. Dịch vụ không muốn dùng một cặp chứng thư/private key cố định được cấp thủ công cho mọi bản triển khai. Thay vào đó:

1. Người vận hành chuẩn bị Vault PKI engine, CA thử nghiệm và role chỉ cho phép cấp chứng thư đúng miền.
2. Workload xác thực với Vault bằng token hoặc auth method được cấp quyền **issue** trên role đó.
3. Spring Vault gọi `VaultPkiOperations.issueCertificate(...)`, nhận chứng thư mới cùng private key tương ứng.
4. Ứng dụng kiểm tra `X509Certificate`, đặc biệt `NotBefore`, `NotAfter`, DNS SAN, EKU và chuỗi tin cậy.
5. Một thành phần quản lý TLS ghi nhận chứng thư đang chạy; trước khi tới `NotAfter`, nó xin chứng thư mới, kiểm tra rồi **chuyển TLS identity**.
6. Ứng dụng thử HTTPS handshake mới bằng certificate mới, giám sát kết quả và xử lý chứng thư cũ theo chính sách.

**Kết quả cần chứng minh:** hai lần cấp có serial number riêng; chứng thư mới hợp lệ và được client tin cậy; kết nối TLS mới dùng chứng thư mới trước khi chứng thư cũ hết hạn; không có private key nào xuất hiện trong log hoặc file không được bảo vệ.

> Mọi tên miền, token, TTL và CA trong bài là **giá trị thử nghiệm**. Không dùng CA dev làm trust anchor của hệ thống production.

## 2. Phân biệt cấp lại chứng thư, lease renewal và CA rotation

Trước khi viết code, cần thống nhất ba khái niệm không đồng nghĩa.

| Việc làm | Đối tượng | Hành vi | Có thay private key của leaf không? |
|---|---|---|---|
| **Re-issue / leaf certificate rotation** | Chứng thư của `orders-api` | Gửi yêu cầu PKI `issue` mới và dùng bundle mới | Có khi Vault sinh cặp khóa mới theo cấu hình role |
| **Renew Vault token** | Token gọi Vault | Kéo dài hoặc thay phiên đăng nhập của ứng dụng | Không |
| **Renew/revoke secret lease** | Lease được Vault quản lý | Gia hạn hoặc thu hồi tài nguyên theo backend | Không mặc nhiên cấp một TLS certificate mới |
| **Rotate CA/issuer** | Khóa/certificate của CA ký | Thay tổ chức tin cậy, issuer và có thể chuỗi CA | Không phải thao tác định kỳ cho từng leaf |

Khi chứng thư TLS sắp hết hạn, **không sửa trực tiếp trường `NotAfter`** và cũng không chỉ gia hạn Vault token. Chứng thư X.509 đã ký không thể thay hạn sử dụng mà vẫn giữ nguyên chữ ký hợp lệ. Cần cấp lại một chứng thư được CA ký và thay TLS material của ứng dụng.

Vault PKI có thể được cấu hình `generate_lease=false`, phổ biến với leaf certificates để giảm chi phí lưu trữ và quản lý leases. Vì thế **đừng dựa vào `lease_duration` hay `lease_renewable` để quyết định chứng thư còn hạn**. Hãy đọc `NotAfter` từ chứng thư X.509 thật. Khi cần thu hồi leaf, sử dụng serial number và PKI revoke API theo quyền được cấp; không nhầm với `sys/leases/revoke` nếu role không cấp lease.

Cũng cần hiểu việc **cấp chứng thư mới không tự thu hồi chứng thư cũ**. Chứng thư cũ thường vẫn có thể được chấp nhận cho tới khi hết hạn hoặc bị thu hồi với cơ chế kiểm tra revocation phù hợp.

## 3. Kiến trúc triển khai và ranh giới trách nhiệm

~~~mermaid
sequenceDiagram
    participant O as Vault operator
    participant V as Vault PKI
    participant A as Java orders-api
    participant T as TLS runtime
    participant C as HTTPS client

    O->>V: Tạo CA test + role orders-server + Vault ACL
    A->>V: Đăng nhập bằng workload identity
    A->>V: POST pki-lab/issue/orders-server
    V-->>A: CertificateBundle #1 + private key #1
    A->>A: Kiểm tra X.509, SAN, EKU, trust chain
    A->>T: Cài TLS identity #1
    C->>T: Handshake kiểm tra hostname và trust
    T-->>C: HTTPS thành công
    Note over A,T: Trước NotAfter một khoảng an toàn
    A->>V: POST issue cho cùng role, yêu cầu mới
    V-->>A: CertificateBundle #2 + private key #2
    A->>A: Kiểm tra chứng thư và private key mới
    A->>T: Chuẩn bị, thử handshake, chuyển identity #2
    C->>T: Handshake TLS mới
    T-->>C: Nhìn thấy serial #2, TLS hợp lệ
    A->>A: Ghi nhận #1 ngừng được phục vụ
    Note over A,V: Revoke #1 khi chính sách yêu cầu và đã chuyển an toàn
~~~

| Thành phần | Trách nhiệm |
|---|---|
| Vault operator | Dựng CA/issuer và PKI role, cấu hình allowed domains, TTL, issuer, policy và trust |
| Workload auth / `SessionManager` | Lấy token có quyền issue và quản lý vòng đời token để tiếp tục gọi Vault |
| `VaultPkiOperations` | Gửi yêu cầu cấp chứng thư theo role, trả `VaultCertificateResponse` |
| Validator | Kiểm tra thời gian hiệu lực, hostname/SAN, mục đích TLS, CA và cặp private key |
| Rotation coordinator | Lập lịch/điều phối cấp lại, chống cấp lặp, xử lý backoff và tình huống lỗi |
| TLS runtime adapter | Cài identity mới vào HTTP server, service mesh, ingress hoặc outbound TLS client phù hợp |
| Client/truststore | Xác thực chuỗi CA, hostname, revocation theo cấu hình |
| Monitoring | Cảnh báo số giờ/ngày còn lại, tỷ lệ issue/activate/handshake lỗi, log request ID đã lọc |

**Spring Vault không tự thay chứng thư trong embedded Tomcat, Jetty, Netty, Envoy hoặc một JDBC client chỉ vì `issueCertificate` đã trả bundle mới.** Bước triển khai vào TLS runtime phải có adapter riêng hoặc dùng cơ chế hot-reload đã được framework/proxy hỗ trợ và kiểm thử.

## 4. Chuẩn bị môi trường thử nghiệm

Một môi trường lab nên có:

- Một Vault dev server hoặc VaultContainer trong Testcontainers, tách khỏi Vault production.
- Một tài khoản/token operator chỉ để chuẩn bị fixture.
- Một token workload chỉ có quyền issue một role, hoặc Kubernetes/AppRole auth được thiết lập đúng trong môi trường test.
- Java 17+ và phiên bản Spring Vault đã được dự án quản lý.
- `openssl` và, nếu dùng shell examples, `jq`.
- Một HTTPS endpoint test có thể thay TLS identity hoặc một test TLS listener riêng.
- CA certificate được lưu trong truststore **riêng của lab**.

Tên trong bài:

| Giá trị | Tên lab |
|---|---|
| PKI mount | `pki-lab/` |
| PKI role | `orders-server` |
| Common Name / DNS SAN | `orders.lab.example.test` |
| Hostname client xác minh | `orders.lab.example.test` |
| CA | `Spring Vault Lab Root CA` |
| Thời hạn leaf đề nghị | `15m` |
| Giới hạn TTL leaf | `45m` |
| Rotation lead time | `5m` trước `NotAfter` |
| Thời hạn root CA demo | `72h` |

`15m` giúp lab có một vòng đời dễ quan sát. Trong kiểm thử tự động, **không đợi đúng 10 phút bằng `Thread.sleep`**; tách quyết định rotation thành hàm thuần dùng `Clock` giả lập, còn luồng cấp mới thực hiện khi test gọi nó.

## 5. Bước 1 — Dựng PKI test CA và role bằng Vault CLI

Thực hiện bằng **operator identity** trên Vault dev/test. Ví dụ cho shell Linux/macOS; cấu hình biến `VAULT_ADDR` và đăng nhập Vault bằng cơ chế test phù hợp trước khi chạy.

~~~bash
# Chỉ bật trong Vault dev/test, không chạy trùng trên mount đã có.
vault secrets enable -path=pki-lab -max-lease-ttl=72h pki

# CA tự ký nội bộ để dựng fixture; KHÔNG tạo root CA demo
# trong production rồi phân phối trust rộng.
vault write pki-lab/root/generate/internal \
  common_name="Spring Vault Lab Root CA" \
  key_type=rsa \
  key_bits=2048 \
  ttl=72h

# Chỉ cấp cho subdomain của lab.example.test.
vault write pki-lab/roles/orders-server \
  allowed_domains="lab.example.test" \
  allow_subdomains=true \
  allow_bare_domains=false \
  allow_wildcard_certificates=false \
  allow_ip_sans=false \
  server_flag=true \
  client_flag=false \
  key_type=rsa \
  key_bits=2048 \
  ttl=15m \
  max_ttl=45m \
  generate_lease=false

vault read pki-lab/roles/orders-server
~~~

Lưu ý:

1. `allowed_domains` kết hợp `allow_subdomains=true` cho phép `orders.lab.example.test`, nhưng `allow_bare_domains=false` không cho xin certificate với CN `lab.example.test`. Cấu hình chặn wildcard/IP SAN tùy mục tiêu quyền.
2. `ttl` là mặc định của role; `max_ttl` giới hạn yêu cầu và còn phụ thuộc mount/system TTL cũng như hạn của issuer. **Không suy ra chứng thư sẽ đúng 900 giây chỉ từ request**: kiểm tra `NotBefore`/`NotAfter` thật.
3. Role cấp server TLS có `server_flag=true` và `client_flag=false`. Kiểm tra Extended Key Usage trong certificate sau cấp; chính sách của hệ thống có thể yêu cầu thêm key usages.
4. Root CA trên một Vault dev instance chỉ là fixture. Production thường cần thiết kế offline root, intermediate CA, HSM/KMS, issuer rotation, AIA/CDP/CRL/OCSP và quy trình quản trị riêng.
5. Khi nhiều issuer trong cùng mount, role và default issuer phải được cấu hình đúng. Đừng để thay đổi default issuer làm certificate mới thuộc chain mà clients chưa tin cậy.

### Kiểm tra CA và trust anchor

Có thể lấy **chỉ chứng thư public** của CA qua endpoint được operator cho phép rồi đưa vào truststore test. CA certificate là dữ liệu public, nhưng nguồn phát hành và fingerprint cần được xác minh.

~~~bash
# Chỉ chứa public CA certificate; ví dụ dành cho lab.
vault read -field=certificate pki-lab/cert/ca > lab-root-ca.pem

# Xem thông tin public; không truy cập khóa riêng root.
openssl x509 -in lab-root-ca.pem \
  -noout -subject -issuer -serial -dates -fingerprint -sha256
~~~

Trong hạ tầng nhiều issuer, đường dẫn public certificate có thể khác; dùng endpoint issuer phù hợp phiên bản Vault. Quan trọng nhất là **client truststore phải có đúng CA được phê duyệt**, không bật `trustAll` hoặc vô hiệu hóa hostname verification để test pass.

## 6. Bước 2 — Tạo policy tối thiểu cho workload

Workload `orders-api` không cần quyền tạo CA, đọc private key của issuer, sửa PKI role hoặc revoke chứng thư của dịch vụ khác. Để xin chứng thư, Vault ACL chỉ cần quyền gửi request tới endpoint issue đúng role.

~~~hcl
# orders-tls-issue.hcl
path "pki-lab/issue/orders-server" {
  capabilities = ["update"]
}
~~~

Tạo policy bằng operator:

~~~bash
vault policy write orders-tls-issue orders-tls-issue.hcl
vault policy read orders-tls-issue
~~~

Nếu dùng Kubernetes auth/AppRole trong production, **gán policy này cho Vault auth role của workload**, rồi đăng nhập bằng identity thực. Trong lab độc lập, có thể tạo một token giới hạn quyền chỉ để test:

~~~bash
# Token ngắn hạn, chỉ dùng ở Vault dev/test.
# Không in token ra CI log; có thể dùng output -format=json
# và lưu trong bộ nhớ fixture test an toàn.
vault token create \
  -policy=orders-tls-issue \
  -no-default-policy \
  -ttl=1h
~~~

Lệnh trên in token vào terminal nên **chỉ thực hiện trong lab cá nhân không ghi hình/log**. Trong CI, dùng API có output được thu thập an toàn, không echo token. Không commit token vào file `application.yml` hoặc báo cáo test.

Dùng workload token để kiểm chứng ranh giới:

~~~bash
vault token capabilities pki-lab/issue/orders-server
vault token capabilities pki-lab/roles/orders-server
vault token capabilities pki-lab/root/generate/internal
vault token capabilities pki-lab/revoke
~~~

Với workload token đúng policy, path `issue` có `update`; các path quản trị role/CA/revoke không được phép. Phải chạy với **token workload thực**, không phải token operator, nếu muốn xác minh ACL.

## 7. Bước 3 — Cấp chứng thư lần đầu

Với workload identity đã đăng nhập Vault, gửi request:

~~~bash
vault write pki-lab/issue/orders-server \
  common_name="orders.lab.example.test" \
  alt_names="orders.lab.example.test" \
  ttl="15m"
~~~

Phản hồi thường có những trường quan trọng:

| Trường | Vai trò |
|---|---|
| `certificate` | PEM chứng thư leaf X.509 |
| `private_key` | **Khóa riêng nhạy cảm** tương ứng với public key của leaf |
| `private_key_type` | Thông tin loại khóa, tùy plugin/phiên bản |
| `issuing_ca` | Chứng thư CA ký |
| `ca_chain` | Chuỗi CA nếu engine trả |
| `serial_number` | Định danh certificate đã phát hành; hữu ích cho log/thu hồi |
| `expiration` | Thời điểm hết hạn ở dữ liệu response, nhưng cần xác minh bằng X.509 |
| `lease_id` / `lease_duration` | Có thể không mang cơ chế gia hạn khi `generate_lease=false` |

**Lệnh `vault write` mặc định có thể in `private_key` ra màn hình.** Trong lab thật, nên dùng output JSON được lưu vào nơi đã giới hạn quyền và tuyệt đối không xuất lên CI log:

~~~bash
# Linux/macOS test shell: thư mục chỉ user hiện tại đọc được.
umask 077
mkdir -p ./lab-pki-private

# File chứa private_key: không commit, không đính kèm ticket/log.
vault write -format=json pki-lab/issue/orders-server \
  common_name="orders.lab.example.test" \
  alt_names="orders.lab.example.test" \
  ttl="15m" > ./lab-pki-private/issued-01.json
~~~

Lệnh trên **cấp một chứng thư mới**, không chỉ hiển thị chứng thư đã cấp ở lệnh trước. Mỗi lệnh issue thành công có thể tạo leaf/khóa mới, cần giới hạn số lần gọi khi chạy CI và tránh retry vô điều kiện.

Chỉ trích xuất **certificate public** để kiểm tra:

~~~bash
jq -r '.data.certificate' ./lab-pki-private/issued-01.json \
  | openssl x509 -noout -subject -issuer -serial -dates \
      -ext subjectAltName,extendedKeyUsage
~~~

Có thể tùy biến câu lệnh `openssl` theo phiên bản và hỗ trợ nhiều `-ext`. Nếu cần xem từng extension, gọi lệnh riêng thay vì đoán từ Subject CN. **TLS hostname verification dựa vào DNS SAN phù hợp**, không chỉ chuỗi Common Name.

## 8. Bước 4 — Cấp chứng thư bằng Spring Vault

Spring Vault cung cấp `VaultPkiOperations`, `VaultCertificateRequest`, `VaultCertificateResponse` và `CertificateBundle`. API chuyên biệt giúp tránh phải tự xử lý nhiều field JSON và định dạng private key.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Objects;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultPkiOperations;
import org.springframework.vault.support.CertificateBundle;
import org.springframework.vault.support.VaultCertificateRequest;
import org.springframework.vault.support.VaultCertificateResponse;

public final class OrdersTlsCertificateIssuer {

    private static final String EXPECTED_DNS =
            "orders.lab.example.test";

    private final VaultPkiOperations pki;

    public OrdersTlsCertificateIssuer(VaultOperations vault) {
        Objects.requireNonNull(vault, "vault");
        this.pki = vault.opsForPki("pki-lab");
    }

    public CertificateBundle issueFreshBundle() {
        VaultCertificateRequest request =
            VaultCertificateRequest.builder()
                .commonName(EXPECTED_DNS)
                .altNames(List.of(EXPECTED_DNS))
                .ttl(Duration.ofMinutes(15))
                .format("pem")
                .build();

        VaultCertificateResponse response =
            pki.issueCertificate("orders-server", request);

        // Không ghi response hay bundle vào log: chứa private key.
        return response.getRequiredData();
    }
}
~~~

Những gì Spring Vault giúp xử lý:

- `opsForPki("pki-lab")` chọn đúng mount.
- `issueCertificate("orders-server", request)` gửi POST tới endpoint issue của role đó.
- `VaultCertificateResponse.getRequiredData()` nhận `CertificateBundle`; nếu không có payload cần thiết, code không tiếp tục với một certificate null.
- `CertificateBundle.getX509Certificate()` chuyển leaf thành `X509Certificate`.
- `CertificateBundle.createKeyStore(...)` tạo `KeyStore` có private key và certificate chain khi cần tích hợp Java TLS.

**Giới hạn:** code giả định `VaultOperations` đã được Spring Boot cấu hình an toàn với Vault URI, TLS CA trust và một workload auth method hợp lệ. Không truyền root token vào issuer class. Kết quả cấp lại **không tự kích hoạt TLS server**; bước chuyển chứng thư là trách nhiệm riêng.

## 9. Bước 5 — Kiểm tra chứng thư trước khi cài vào TLS runtime

Không lấy bất kỳ chứng thư nào được trả về rồi gắn ngay vào production endpoint. Ít nhất cần kiểm tra:

1. Chứng thư đã có hiệu lực (`NotBefore` không ở tương lai vượt giới hạn clock skew) và chưa hết hạn.
2. `NotAfter` còn đủ xa để triển khai/kiểm thử/rollback trước khi hết hạn.
3. DNS SAN chứa **đúng hostname cần phục vụ**, không chỉ dựa vào Subject CN.
4. Leaf không phải CA certificate (`basicConstraints`), có EKU `serverAuth` khi policy yêu cầu.
5. Certificate chain dẫn về **CA đã được client/truststore phê duyệt**.
6. Private key có mặt và khớp public key của leaf; một handshake thử phải chứng minh điều này.
7. Serial number khác certificate đang được phục vụ khi test kiểm chứng lần cấp mới.
8. Certificate không thuộc CA/issuer không được mong đợi sau thay đổi cấu hình Vault.

### Java: kiểm tra X.509 thời gian, SAN, EKU

~~~java
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

public final class OrdersCertificateValidator {

    private static final String SERVER_AUTH_EKU =
            "1.3.6.1.5.5.7.3.1";

    public void validateLeaf(
            X509Certificate certificate,
            String expectedDns,
            Clock clock,
            Duration requiredRemaining) throws CertificateException {

        Objects.requireNonNull(certificate);
        Objects.requireNonNull(clock);
        Instant now = clock.instant();

        certificate.checkValidity(java.util.Date.from(now));

        if (!certificate.getNotAfter().toInstant()
                .isAfter(now.plus(requiredRemaining))) {
            throw new CertificateException(
                "Certificate validity is too short for safe rollout");
        }

        if (certificate.getBasicConstraints() >= 0) {
            throw new CertificateException("Expected an end-entity leaf");
        }

        List<String> eku = certificate.getExtendedKeyUsage();
        if (eku == null || !eku.contains(SERVER_AUTH_EKU)) {
            throw new CertificateException("serverAuth EKU missing");
        }

        Collection<List<?>> sans = certificate.getSubjectAlternativeNames();
        if (sans == null) {
            throw new CertificateException("DNS SAN missing");
        }

        Set<String> dnsNames = sans.stream()
                .filter(x -> x.size() >= 2 && Integer.valueOf(2).equals(x.get(0)))
                .map(x -> String.valueOf(x.get(1)).toLowerCase(java.util.Locale.ROOT))
                .collect(Collectors.toSet());

        // Lab yêu cầu đúng một DNS name, không có wildcard/host ngoài phạm vi.
        if (!dnsNames.equals(Set.of(
                expectedDns.toLowerCase(java.util.Locale.ROOT)))) {
            throw new CertificateException("Unexpected DNS SAN set");
        }

        // Production cần bổ sung kiểm tra CA chain/trust anchor,
        // các SAN type khác và TLS handshake bằng chính private key.
    }
}
~~~

Mẫu trên kiểm tra DNS SAN nhưng **chưa thay thế** `TrustManager` / PKIX path validation. Với production phải kiểm tra chain đến trust anchor đã pin/cấu hình, các name types khác (IP/URI nếu có), extension policy và revocation theo yêu cầu. Trường hợp kiểm thử chỉ cho phép đúng hostname, cũng nên từ chối bất kỳ SAN type ngoài dự kiến thay vì chỉ kiểm tra tập DNS.

Có thể bổ sung:

~~~java
X509Certificate leaf = bundle.getX509Certificate();
X509Certificate issuer = bundle.getX509IssuerCertificate();

leaf.verify(issuer.getPublicKey());

// Đây chỉ kiểm tra chữ ký bằng key của issuer trả về;
// KHÔNG chứng minh issuer là CA đáng tin cậy.
// Phải so sánh/validate với CA truststore đã được duyệt.
~~~

**Không tin cậy một CA chỉ vì nó đi kèm trong response từ API.** Nếu tin tưởng mọi CA do server đưa ra, kiểm thử TLS có thể “pass” với issuer bị thay sai.

## 10. Xác định khi nào chứng thư sắp hết hạn

Có hai loại thời gian:

- `NotBefore` và `NotAfter` trong leaf X.509: khoảng hiệu lực thực tế của chứng thư.
- Vault token TTL/lease TTL: vòng đời đăng nhập và lease riêng của Vault.

Quyết định thay certificate dựa vào **`NotAfter`**, có thể xét thêm `NotBefore`, clock skew, thời gian triển khai và rủi ro Vault tạm ngắt. Một công thức dễ kiểm thử:

~~~text
remaining = NotAfter - now
rotate_when = remaining <= rotation_lead_time
~~~

Ví dụ:

| Thời điểm minh họa | NotAfter còn lại | Lead time = 5m | Hành động |
|---|---|---|---|
| Vừa cấp | 15m | 5m | Dùng chứng thư hiện tại |
| Sau khoảng 8m | 7m | 5m | Tiếp tục phục vụ, kiểm tra định kỳ |
| Sau khoảng 10m | 5m | 5m | Bắt đầu cấp mới |
| Sau khoảng 12m | 3m | 5m | Nếu cấp mới thất bại, tăng mức cảnh báo và retry có giới hạn |
| Sau 15m | 0 | 5m | Chứng thư đã hết hạn; **không** coi là fallback hợp lệ |

Thời gian trên chỉ minh họa; CA và role có thể điều chỉnh `NotAfter` thực. Chọn lead time dựa vào TTL thực tế, độ trễ phát hành, chu kỳ kiểm tra, mất mạng, số instance và yêu cầu SLA. Với chứng thư sống nhiều ngày, cần lead time đủ lớn để sửa sự cố. Với TTL ngắn, độ trễ và jitter của lịch kiểm tra phải nhỏ hơn khoảng an toàn.

### Java: hàm thuần quyết định cần rotation

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class CertificateRotationWindow {

    private CertificateRotationWindow() {
    }

    public static boolean isDue(
            Instant now,
            Instant notAfter,
            Duration leadTime) {

        Objects.requireNonNull(now);
        Objects.requireNonNull(notAfter);
        Objects.requireNonNull(leadTime);

        if (leadTime.isNegative()) {
            throw new IllegalArgumentException("leadTime must not be negative");
        }

        return !now.plus(leadTime).isBefore(notAfter);
    }
}
~~~

Hàm này trả `true` cả khi đã hết hạn. Điều đó đúng cho quyết định **cần thay ngay**, nhưng không cho phép tiếp tục dùng chứng thư cũ đã hết hạn. Tầng kích hoạt TLS phải kiểm soát riêng failure policy.

## 11. Thử nghiệm bằng Clock thay vì chờ TTL thật

Đối với hàm quyết định, dùng JUnit 5 và `Instant` cố định:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class CertificateRotationWindowTest {

    private static final Instant ISSUED =
            Instant.parse("2026-11-25T10:00:00Z");
    private static final Instant EXPIRES =
            ISSUED.plus(Duration.ofMinutes(15));
    private static final Duration LEAD = Duration.ofMinutes(5);

    @Test
    void notDueImmediatelyAfterIssuance() {
        assertFalse(CertificateRotationWindow.isDue(
                ISSUED, EXPIRES, LEAD));
    }

    @Test
    void dueExactlyAtSafetyWindow() {
        Instant now = ISSUED.plus(Duration.ofMinutes(10));

        assertTrue(CertificateRotationWindow.isDue(
                now, EXPIRES, LEAD));
    }

    @Test
    void overdueAfterExpiration() {
        assertTrue(CertificateRotationWindow.isDue(
                EXPIRES.plusSeconds(1), EXPIRES, LEAD));
    }
}
~~~

Đây là unit test **lịch rotation**, không chứng minh Vault đã cấp chứng thư hay HTTPS server đã chuyển certificate. Phần cấp chứng thư và TLS handshake cần integration test riêng với Vault thật.

Trong production, thay vì dựa vào một đồng hồ của pod duy nhất, cần NTP/đồng hồ ổn định và theo dõi clock drift. Nếu ứng dụng chạy nhiều instance, thêm jitter hợp lý trước thời điểm rotation hoặc chỉ định một cơ chế điều phối khi mọi instance chia sẻ cùng TLS material, tránh đồng loạt issue quá nhiều certificates.

## 12. Bước 6 — Cấp bundle thứ hai và xác minh nó khác bundle cũ

Gọi `issueCertificate` lần nữa **với cùng role và CN/SAN hợp lệ** là thao tác **cấp một chứng thư mới**, không phải kéo dài thời gian của bundle cũ.

~~~java
OrdersTlsCertificateIssuer issuer =
        new OrdersTlsCertificateIssuer(vaultOperations);

CertificateBundle first = issuer.issueFreshBundle();
CertificateBundle second = issuer.issueFreshBundle();

String oldSerial = first.getSerialNumber();
String newSerial = second.getSerialNumber();

if (oldSerial.equals(newSerial)) {
    throw new IllegalStateException(
        "Expected a distinct certificate after re-issuance");
}

java.time.Instant oldNotAfter =
        first.getX509Certificate().getNotAfter().toInstant();

java.time.Instant newNotAfter =
        second.getX509Certificate().getNotAfter().toInstant();
~~~

Không assert `newNotAfter > oldNotAfter` **tuyệt đối** khi hai request được gửi sát nhau: cả hai có thể cùng thời điểm hết hạn tính theo độ chính xác giây hoặc bị giới hạn bởi CA. Điều cần chứng minh là chứng thư mới có **serial mới**, đúng DNS SAN, chain hợp lệ và `NotAfter` đủ xa so với thời điểm triển khai.

Nếu issuer trả certificate có thời gian sống quá ngắn vì CA gần hết hạn, **không kích hoạt** bundle đó chỉ để cho quy trình test pass. Điều tra TTL role, mount, issuer `NotAfter` và yêu cầu rotation của CA theo chính sách vận hành.

## 13. Bước 7 — Chuẩn bị identity TLS trong Java

`CertificateBundle` cung cấp chứng thư và private key. Spring Vault hỗ trợ:

~~~java
import java.security.KeyStore;
import org.springframework.vault.support.CertificateBundle;

CertificateBundle bundle = issuer.issueFreshBundle();

// Password được cấp bởi secret manager của lab/application.
// Không hardcode mật khẩu thật trong source.
char[] keyPassword = passwordSupplier.get();

try {
    KeyStore keyStore =
            bundle.createKeyStore("orders-tls", keyPassword);

    // Adapter TLS runtime sẽ dùng KeyStore để tạo/cài KeyManager.
    // Không xuất KeyStore có private key sang log hoặc file mở quyền rộng.
    tlsIdentityInstaller.prepare(keyStore, keyPassword);
} finally {
    java.util.Arrays.fill(keyPassword, '\0');
}
~~~

Đây là **trích đoạn tích hợp**: `passwordSupplier` và `tlsIdentityInstaller` do ứng dụng triển khai; không phải API Spring Vault tự có. `passwordSupplier.get()` phải cung cấp một mảng `char[]` mới do caller sở hữu, không phải buffer được chia sẻ với bean khác, vì đoạn `finally` sẽ xóa chính mảng đó. `prepare` phải hoàn tất phần tiêu thụ key password đồng bộ trước khi đoạn code xóa `char[]`. Nếu adapter lưu password để sử dụng sau, nó phải quản lý bản sao được bảo vệ và lifecycle riêng.

Đối với Java TLS có thể dùng `KeyManagerFactory` và `SSLContext`:

~~~java
import java.security.KeyStore;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;

KeyManagerFactory kmf =
    KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());

kmf.init(keyStore, keyPassword);

SSLContext candidateContext = SSLContext.getInstance("TLS");
candidateContext.init(kmf.getKeyManagers(), trustManagers, null);
~~~

Trong đoạn trên `trustManagers` là tập tin cậy đã được ứng dụng cấu hình và kiểm chứng; không khởi tạo `TrustManager` chấp nhận mọi certificate. Một `SSLContext` mới chứa identity mới **không đồng nghĩa** embedded server đang chạy đã chuyển sang dùng nó. Phải kết nối `candidateContext` với HTTP server connector hoặc client connection factory theo API và phiên bản cụ thể.

### Phân biệt inbound server TLS và outbound mTLS

| Kịch bản | Thành phần thật sự cần chuyển identity | Điều kiểm thử sau chuyển |
|---|---|---|
| Embedded Tomcat/Jetty/Netty phục vụ HTTPS | Server connector / SSL bundle / key manager phù hợp | Client mới thấy leaf serial mới |
| Java HTTP client dùng mTLS | HTTP client/connection manager và key managers | Server nhận chứng thư client mới trong handshake |
| Ingress/Envoy/Service mesh terminate TLS | Ingress/secret watcher/sidecar hoặc control plane | Endpoint ingress gửi serial mới; app JVM có thể không giữ private key |
| Kubernetes Secret volume + file watcher | Controller/agent cập nhật file và runtime reload | Tệp mới đã vào pod và server thực sự load lại |
| Spring Cloud Vault Config Data | Property source / bean configuration nếu có refresh | Chỉ cập nhật property **không** đủ chứng minh TLS connector đã reload |

Nếu HTTPS được terminate bởi ingress, code Java có thể **không nên quản lý TLS identity ở JVM**. Khi ấy dùng controller/agent/cert-manager/Vault Secrets Operator phù hợp để cập nhật TLS Secret và reload ingress. Bài lab Java tập trung vào trường hợp ứng dụng trực tiếp quản lý TLS material.

## 14. Quy trình chuyển chứng thư an toàn: prepare → probe → promote

Một cơ chế rotation đáng tin cậy không nên ghi đè key store đang dùng rồi hy vọng server tự tiếp nhận. Cần hai giai đoạn:

~~~mermaid
flowchart TD
    A["Đang dùng certificate #1"] --> B{"Đã vào lead time?"}
    B -->|Chưa| A
    B -->|Có| C["Xin bundle #2 từ Vault PKI"]
    C --> D["Kiểm tra X.509, SAN, CA chain, private key"]
    D --> E{"Hợp lệ và đủ hạn?"}
    E -->|Không| F["Không kích hoạt, cảnh báo và retry có giới hạn"]
    E -->|Có| G["Stage TLS identity #2"]
    G --> H["Handshake probe/test traffic"]
    H --> I{"Probe thành công?"}
    I -->|Không| F
    I -->|Có| J["Promote identity #2 atomically hoặc rollout an toàn"]
    J --> K["Handshake mới thấy serial #2"]
    K --> L["Dừng dùng #1 cho kết nối mới"]
    L --> M["Dọn material #1; revoke nếu chính sách yêu cầu"]
~~~

Các bước:

1. **Prepare:** xin bundle mới một lần, validate X.509, xây `KeyStore` hoặc cấu hình tương đương.
2. **Probe:** kiểm tra certificate/private key tương thích, thử TLS handshake trên endpoint thử hoặc canary và xác nhận đúng hostname, đúng CA và serial mong đợi.
3. **Promote:** kích hoạt một identity mới hoàn chỉnh, tránh trạng thái nửa chứng thư cũ/nửa private key mới.
4. **Observe:** theo dõi HTTPS handshake và TLS errors sau chuyển.
5. **Retire:** ngừng sử dụng material cũ cho kết nối mới, drain kết nối cũ theo chính sách.
6. **Cleanup:** xóa bản copy/private key cũ khỏi file/keystore cần dọn; revoke certificate cũ **nếu** chính sách và revocation infrastructure yêu cầu.

**Không revoke chứng thư cũ trước khi probe và promote thành công**, trừ trường hợp khẩn cấp như khóa cũ bị lộ. Khi chuyển thất bại mà chứng thư cũ còn hiệu lực, có thể giữ chứng thư cũ trong một khoảng **grace period** ngắn và cảnh báo. Nếu chứng thư cũ đã hết hạn hoặc bị thu hồi, không nên rollback sang nó.

### Interface điều phối ở tầng ứng dụng

~~~java
import java.security.KeyStore;
import java.security.cert.X509Certificate;

public interface TlsIdentityInstaller {

    interface StagedIdentity {
    }

    // Stage mà không ảnh hưởng identity đang phục vụ.
    StagedIdentity stage(
        KeyStore keyStore,
        char[] privateKeyPassword,
        X509Certificate leaf) throws Exception;

    // Kiểm tra key pair, trust chain và handshake thử.
    void probe(
        StagedIdentity candidate,
        String expectedHostname) throws Exception;

    // Bật certificate mới cho các handshake sau.
    void activate(StagedIdentity candidate) throws Exception;
}
~~~

Đây là **hợp đồng adapter mẫu**, không phải interface có sẵn của Spring Vault. Nó giúp thay implementer khi chuyển từ embedded Tomcat sang Netty, service mesh hoặc TLS client. Việc `activate` có atomic hoàn toàn không phụ thuộc chỉ vào interface; cần đánh giá hành vi thực tế của connector.

## 15. Coordinator cấp mới khi vào cửa sổ an toàn

Đoạn mã sau ghép issuance, validation và installer, nhưng **không giả vờ** Spring Vault tự hot-reload TLS. Runtime phải cung cấp triển khai `TlsIdentityInstaller` và cơ chế persistence/checkpoint phù hợp trước khi đưa vào production.

~~~java
import java.security.KeyStore;
import java.security.cert.X509Certificate;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.function.Supplier;

import org.springframework.vault.support.CertificateBundle;

public final class OrdersTlsRotationCoordinator {

    private static final String DNS_NAME = "orders.lab.example.test";

    private final OrdersTlsCertificateIssuer issuer;
    private final OrdersCertificateValidator validator;
    private final TlsIdentityInstaller installer;
    private final Supplier<char[]> keyPasswordSupplier;
    private final Clock clock;
    private final Duration leadTime;

    private X509Certificate activeLeaf;

    public OrdersTlsRotationCoordinator(
            OrdersTlsCertificateIssuer issuer,
            OrdersCertificateValidator validator,
            TlsIdentityInstaller installer,
            Supplier<char[]> keyPasswordSupplier,
            Clock clock,
            Duration leadTime) {

        this.issuer = Objects.requireNonNull(issuer);
        this.validator = Objects.requireNonNull(validator);
        this.installer = Objects.requireNonNull(installer);
        this.keyPasswordSupplier = Objects.requireNonNull(keyPasswordSupplier);
        this.clock = Objects.requireNonNull(clock);
        this.leadTime = Objects.requireNonNull(leadTime);
    }

    public synchronized boolean rotateIfDue() throws Exception {
        Instant now = clock.instant();

        if (activeLeaf != null &&
            !CertificateRotationWindow.isDue(
                now, activeLeaf.getNotAfter().toInstant(), leadTime)) {
            return false;
        }

        // POST issue tạo certificate mới; không gọi lặp vô hạn khi lỗi.
        CertificateBundle fresh = issuer.issueFreshBundle();
        X509Certificate candidate = fresh.getX509Certificate();

        validator.validateLeaf(
            candidate, DNS_NAME, clock, leadTime);

        char[] password = keyPasswordSupplier.get();
        if (password == null || password.length == 0) {
            throw new IllegalStateException("Key password unavailable");
        }

        try {
            KeyStore keyStore =
                fresh.createKeyStore("orders-tls", password);

            TlsIdentityInstaller.StagedIdentity staged =
                installer.stage(keyStore, password, candidate);

            installer.probe(staged, DNS_NAME);
            installer.activate(staged);

            // Chỉ cập nhật trạng thái sau khi activate được xác nhận.
            activeLeaf = candidate;
            return true;
        } finally {
            java.util.Arrays.fill(password, '\0');
        }
    }
}
~~~

Ý nghĩa và giới hạn:

- `synchronized` ngăn hai thread trong **cùng coordinator instance** đồng thời issue và activate. Nó **không** tạo khóa phân tán giữa nhiều pod.
- `activeLeaf` ở bộ nhớ mất khi JVM restart. Production cần lấy identity thực tế từ runtime/persistent keystore hoặc thiết kế warm-start; không mặc định khởi động lại là phải cấp vô hạn.
- `stage/probe/activate` do môi trường TLS triển khai, có thể gồm canary listener/HTTPS endpoint và kiểm tra serial. Một số connector chỉ thay certificate cho **handshake mới**, không đóng connection cũ.
- Một phản hồi issue bị timeout có thể vẫn đã tạo certificate ở Vault. Retry cần backoff/jitter, giới hạn số lần cấp và quan sát audit, không vòng lặp liên tục.
- Nếu `activate` đã thay runtime nhưng sau đó báo exception, cần xác minh identity thực tế trước retry/rollback; trạng thái in-memory không phải chứng cứ duy nhất.
- Không lưu toàn bộ `CertificateBundle` trong các DTO có `toString()` hoặc actuator/configprops exposure.

### Lập lịch trong Spring Boot

Một ứng dụng có thể tạo scheduler dùng `@Scheduled(fixedDelayString=...)` gọi `rotateIfDue()`. Đặt tần suất nhỏ hơn lead time, ví dụ mỗi phút trong lab có TTL 15 phút. Scheduler phải catch và phân loại lỗi, xuất metric/cảnh báo, không log `CertificateBundle` hoặc private key.

Một ứng dụng nhiều instance có thể **mỗi instance có chứng thư riêng** và tự thay hoặc sử dụng một secret delivery controller chung. Phải xác định model từ đầu; không sử dụng một job duy nhất rồi giả định mọi pod đã nhận certificate mới.

## 16. Bước 8 — Kiểm chứng TLS handshake sau khi thay thế

**Certificate được cấp đúng chưa đủ.** Mục tiêu bài học là chứng thư **đang được phục vụ** đã đổi.

Sau khi `activate` thành công trên HTTPS listener test, từ client có truststore lab:

~~~bash
# Hostname phải phân giải đến HTTPS endpoint test thật.
# Không dùng -k để bỏ qua xác thực certificate.
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername orders.lab.example.test \
  -verify_hostname orders.lab.example.test \
  -CAfile lab-root-ca.pem \
  -showcerts < /dev/null
~~~

Lưu ý:

- `-servername` gửi SNI hostname; `-verify_hostname` xác nhận tên được phục vụ; `-CAfile` xác nhận trust anchor test.
- `-connect 127.0.0.1:8443` chỉ là endpoint local minh họa; listener thật có thể ở cổng khác hoặc ingress.
- Kiểm tra mã xác thực cuối `Verify return code: 0 (ok)` cùng certificate details. Không chỉ kiểm tra lệnh TCP kết nối thành công.
- Xem serial/NotAfter của **leaf đang phát**. Có thể dùng `openssl x509 -noout -serial -dates -ext subjectAltName` trên certificate public được trích xuất, tránh in private key.
- Nếu kết nối qua load balancer nhiều backend, lặp lại kiểm tra theo từng backend/instance hoặc dùng probe/telemetry biết instance nào đã chuyển.

### Kết quả kỳ vọng

| Kiểm tra | Trước thay | Sau thay |
|---|---|---|
| TLS handshake với lab CA | Thành công | Thành công |
| DNS SAN | `orders.lab.example.test` | Vẫn đúng |
| Serial number leaf | `serial_1` | `serial_2` (khác) |
| `NotAfter` | Đang gần cửa sổ lead time | Còn thời gian đủ cho rollout tiếp |
| Key pair | Certificate #1 khớp key #1 | Certificate #2 khớp key #2 |
| Log | Metadata serial, NotAfter, outcome | Metadata mới, không có private key |
| Kết nối cũ | Có thể đang mở | Có thể còn mở đến khi drain/timeout |

Một listener cố định chứng thư lúc startup **không tự đổi** chỉ vì ứng dụng tạo `SSLContext` mới. Nếu serial qua handshake vẫn là `serial_1`, tác vụ thay thế **chưa hoàn tất** dù coordinator đã có bundle #2.

## 17. Bước 9 — Khi nào thu hồi chứng thư cũ?

Cần tách hai tình huống:

**Rotation bình thường:** Chứng thư cũ gần hết hạn, private key không bị lộ. Có thể chờ đến khi mọi instance/channels đã chuyển rồi cho chứng thư cũ tự hết hạn, hoặc thu hồi theo chính sách nếu hạ tầng hỗ trợ CRL/OCSP được clients kiểm tra.

**Khóa bị lộ hoặc certificate bị cấp sai:** Có thể cần thu hồi ngay bằng serial, cập nhật CRL/OCSP và thay certificate khẩn cấp. Lúc đó không được rollback sang certificate/key đã bị compromise.

Spring Vault có API:

~~~java
import org.springframework.vault.core.VaultPkiOperations;

VaultPkiOperations pki = vaultOperations.opsForPki("pki-lab");

// Chỉ hoạt động khi token có quyền revoke theo policy riêng.
pki.revoke(oldCertificateSerialNumber);
~~~

Workload token `orders-tls-issue` **không có quyền revoke** trong ví dụ; hành động trên thuộc workflow vận hành được ủy quyền khác, không phải tự động cấp quyền rộng cho mọi app. Revocation bằng serial khác với hủy một Vault token và không đồng nghĩa tất cả client đã được cấu hình để kiểm tra CRL/OCSP.

Nếu chỉ dùng `generate_lease=false`, certificate không nhất thiết có lease để renew/revoke qua lease APIs. **PKI revoke API** vẫn có thể áp dụng theo cấu hình engine, việc certificate có được lưu lại và khả năng thu hồi phải được kiểm chứng.

## 18. Ma trận kiểm thử tích hợp

Để nghiệm thu, dựng Vault test với PKI mount/role giống setup, dùng workload token riêng và một HTTPS listener hoặc TLS runtime có thể kiểm tra identity đã cài.

| Ca | Tình huống | Điều kiện đạt |
|---|---|---|
| P01 | Workload issue CN/SAN đúng role | Nhận `CertificateBundle`, leaf hợp lệ, có private key |
| P02 | X509 validation | SAN chính xác, serverAuth EKU, đúng CA, `NotAfter` đủ dài |
| P03 | Clock chưa vào lead time | Không phát lệnh issue mới |
| P04 | Clock chạm lead time | Coordinator cấp mới với serial khác |
| P05 | Candidate được stage/probe | Handshake test thành công bằng CA truststore |
| P06 | Activate candidate | Handshake mới tới endpoint thật trả `serial_2` |
| P07 | Chuyển ở nhiều instance | Mọi backend mục tiêu đều dùng leaf mới |
| N01 | CN ngoài `lab.example.test` | Vault PKI role từ chối |
| N02 | Wildcard hoặc IP SAN không được phép | Vault PKI role từ chối |
| N03 | Workload cố sửa role/CA | Vault ACL từ chối |
| N04 | Candidate có SAN sai/issuer lạ/NotAfter quá gần | Không activate |
| N05 | TLS probe fail | Giữ identity cũ **nếu còn hợp lệ**, cảnh báo |
| N06 | Vault tạm mất kết nối | Retry có giới hạn, không lộ secrets |
| N07 | Chứng thư cũ đã hết hạn | Không rollback/tiếp tục phục vụ như chứng thư hợp lệ |
| N08 | Token expired nhưng leaf vẫn hợp lệ | Auth/session được xử lý riêng; kiểm tra retry cấp mới |
| N09 | Hai scheduler tick cùng thời điểm | Không issue trùng trong một coordinator |
| S01 | Kiểm tra log/metrics | Không chứa private key, token, raw PKI response |

Một lỗi handshake với certificate cũ chưa hết hạn phải được phân biệt với lỗi TLS trust CA hoặc client chỉ kết nối đến một backend chưa cập nhật.

### JUnit 5: chứng minh hai issuance khác serial

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.CertificateBundle;

@SpringBootTest
class PkiRotationIntegrationTest {

    @Autowired
    private VaultOperations vault;

    @Test
    void reissueProducesAnotherValidLeafCertificate() throws Exception {
        OrdersTlsCertificateIssuer issuer =
                new OrdersTlsCertificateIssuer(vault);

        OrdersCertificateValidator validator =
                new OrdersCertificateValidator();

        CertificateBundle first = issuer.issueFreshBundle();
        CertificateBundle second = issuer.issueFreshBundle();

        assertNotNull(first.getPrivateKey());
        assertNotNull(second.getPrivateKey());
        assertNotEquals(
                first.getSerialNumber(),
                second.getSerialNumber());

        validator.validateLeaf(
                first.getX509Certificate(),
                "orders.lab.example.test",
                Clock.systemUTC(),
                Duration.ofMinutes(5));

        validator.validateLeaf(
                second.getX509Certificate(),
                "orders.lab.example.test",
                Clock.systemUTC(),
                Duration.ofMinutes(5));
    }
}
~~~

**Điều kiện chạy:** test cần Vault thật/test container, CA và role đã tạo, token có `update` ở đúng issue path, đồng hồ hai máy tương đối đồng bộ. Thử serial khác không chứng minh TLS listener đã reload; **P06 phải có một phép kiểm chứng handshake** với listener được cấu hình bởi adapter.

Không dùng unit test Mockito trả hai `CertificateBundle` giả để thay thế kiểm tra role, SAN, TTL và quyền ACL của Vault. Có thể dùng Mockito cho những unit tests quyết định rotation hoặc lỗi `TlsIdentityInstaller`, nhưng phần issue/ACL/PKI phải gọi server thật.

## 19. Kiểm thử các lỗi và quyết định rollback

| Lỗi | Có được dùng lại leaf cũ? | Hành động |
|---|---|---|
| Vault API 403 | Nếu leaf cũ **còn hạn, chưa bị revoke** | Cảnh báo ACL/workload auth, không mở rộng quyền bừa |
| Vault chưa reachable | Nếu leaf cũ còn hạn | Retry bounded/backoff, kiểm tra Vault health/TLS |
| PKI role từ chối CN/SAN | Nếu leaf cũ còn hạn | Sửa dữ liệu yêu cầu/role đúng chính sách |
| Candidate chain không được tin cậy | Có, khi leaf cũ vẫn hợp lệ | Không promote; kiểm tra issuer/truststore/CA rotation |
| Candidate key mismatch | Có, khi leaf cũ vẫn hợp lệ | Không promote; kiểm tra keystore material |
| Activation lỗi ở một backend | Theo trạng thái **thật** của backend | Kiểm tra serial đang phục vụ, canary/rollback từng instance |
| Leaf cũ đã expired | **Không** | Fail closed hoặc khôi phục bằng identity mới hợp lệ |
| Private key cũ bị compromise | **Không** | Revoke theo runbook, thay khóa và điều tra |
| NotAfter mới không kéo dài đủ | Có, nếu leaf cũ còn hạn | Điều tra issuer NotAfter, role TTL/mount cap |
| Token/lease renewal lỗi | Có thể leaf cũ vẫn còn hạn | Phân biệt lỗi đăng nhập Vault với hiệu lực leaf |

**Lưu ý:** retry `issue` không có idempotency key theo mặc định. Nếu mất response sau khi Vault đã cấp, lặp lại request có thể tạo thêm certificates và serial numbers. Có giới hạn số attempts, backoff, jitter và giám sát cấp phát. Không nên gọi issue mỗi HTTP request hay mỗi TLS handshake.

## 20. Giám sát quá trình rotation

Khi vận hành, đo những chỉ số ít nhạy cảm:

| Metric/log field | Ý nghĩa | Lưu ý |
|---|---|---|
| `tls_cert_seconds_until_expiry` | Số giây còn lại tới `NotAfter` | Gauge theo service/instance/role loại cố định |
| `pki_issue_attempts_total` | Số lần gọi issue | Counter theo outcome và role đã chuẩn hóa |
| `pki_issue_duration_seconds` | Thời gian gọi Vault PKI | Histogram/timer |
| `tls_cert_activation_total` | Số lần activate thành công/thất bại | Có nhãn outcome |
| `tls_handshake_failures_total` | Lỗi TLS sau rotation | Theo loại lỗi giới hạn cardinality |
| `vault_request_id` | ID cho một lần issue | Chỉ log/traces; **không** làm metric label |
| `certificate_serial` | Đối chiếu chứng thư đang phục vụ | Chỉ log/record được bảo vệ, không làm nhãn metric cardinality cao |
| `not_after` | Hạn certificate đang được phục vụ | Có thể log dạng thời điểm, không chứa private key |

Không log `private_key`, `CertificateBundle.toString()`, token, Vault raw response, CSR chứa định danh nhạy cảm hoặc keystore bytes. Serial/public leaf certificate thông thường không phải secret, nhưng vẫn có thể tiết lộ tên hệ thống và lịch triển khai; chỉ giữ trong hệ thống quan sát được kiểm soát.

Một mức cảnh báo ví dụ (điều chỉnh theo TTL và SLA):

~~~text
INFO:  remaining > lead_time
WARN:  remaining <= lead_time và chưa có candidate active
ERROR: remaining <= critical_margin hoặc rotation liên tục thất bại
PAGE:  certificate đã hết hạn hoặc TLS handshake với truststore đúng thất bại
~~~

Đừng coi `issue success` là SLI đủ; **active serial từ TLS handshake mới** và `seconds_until_expiry` mới là bằng chứng rotation đã thực sự hoàn tất.

## 21. CI/CD và môi trường thử nghiệm

Một pipeline đáng tin cậy nên có ba tầng:

1. **Unit tests:** quyết định lead time, logic không cấp lại khi chưa cần, retry/backoff, lỗi stage/probe; dùng `Clock` giả lập, không cần Vault.
2. **Vault integration tests:** dùng Testcontainers Vault dev với PKI CA/role fixture; xác minh issue, serial mới, SAN/TTL, negative ACL; không dùng production root token.
3. **TLS end-to-end tests:** kết nối tới HTTPS listener test thật, xác minh trust chain và hostname, quan sát serial trước/sau activate; kiểm tra load balancer nhiều instance nếu có.

Các yếu tố cần kiểm soát trong CI:

- Pin Vault image và các phiên bản Spring Boot/Spring Vault; không dùng image tag `latest` để tái lập lỗi.
- Dùng port động, CA và namespace logic test riêng; không giao root token thật cho runner.
- Không đưa JSON issue response chứa private key vào CI artifact hoặc console.
- Tránh chờ 15 phút trong unit test. Với integration test chỉ cần xin hai leaf nối tiếp để xác nhận issuance; dùng `Clock.fixed` để test điều kiện thời gian.
- Có health/readiness check cho Vault; phân biệt container chưa sẵn sàng với ACL 403.
- Xóa container, các file JSON/PEM/keystore tạm và tokens test khi job kết thúc.
- Nếu dùng PKI certificate private keys dưới dạng file, đặt thư mục quyền chặt, xóa sau test; với production nên ưu tiên cơ chế phân phối secret được duyệt.
- Nếu đang dùng Kubernetes ingress/service mesh, chạy một E2E test cho **controller/agent hot reload** chứ không chỉ kiểm tra JVM TLS.

## 22. Bài tập nâng cao và tiêu chí nghiệm thu

### Bài A — Cấp lần đầu và xác minh chứng thư

Dựng `pki-lab`, role `orders-server` và token workload theo mục 5–7. Cấp một certificate cho `orders.lab.example.test`, đọc thông tin public leaf bằng OpenSSL và `X509Certificate`. Xác minh DNS SAN, EKU `serverAuth`, NotBefore, NotAfter và issuer.

**Đạt** khi request hợp lệ thành công và workload không đọc/sửa được role hay CA.

### Bài B — Thay khi còn năm phút

Trong Java, lưu `NotAfter` của leaf đang được TLS runtime dùng. Dùng `CertificateRotationWindow.isDue`, viết test tại `remaining=6m`, `remaining=5m` và `remaining=4m`. Khi tới cửa sổ, gọi issue lần nữa, validate và stage candidate.

**Đạt** khi lịch không cấp trước ngưỡng, cấp đúng một candidate khi vào ngưỡng theo mỗi coordinator và không chờ đồng hồ thật trong unit test.

### Bài C — Thay chứng thư cho HTTPS listener

Triển khai `TlsIdentityInstaller` cho một HTTPS listener test. Trước promote, client kiểm tra leaf serial #1. Sau promote, client dùng CA truststore đã kiểm chứng và hostname verification để handshake; serial phải là #2.

**Đạt** khi cả trust verification và serial change đều đúng, không sử dụng `-k`/`trustAll`.

### Bài D — Kiểm thử negative/failure

Thử CN sai miền, wildcard không được phép, token thiếu `update`, Vault không reachable, candidate chain sai, installer probe thất bại. Ở mọi tình huống, không activate certificate sai; nếu leaf cũ hết hạn, hệ thống phải fail closed thay vì trả về HTTPS “thành công” bằng chứng thư không hợp lệ.

**Đạt** khi log/metrics có tín hiệu lỗi và không chứa token/private key.

### Bài E — Phân biệt leaf rotation và issuer rotation

Giả sử operator bắt đầu chuyển intermediate CA. Hãy thiết kế một timeline phân phối trust chain trước khi cấp leaf dưới issuer mới; giữ CA cũ đủ lâu để các certificate còn hiệu lực được validate hoặc thu hồi theo runbook. Kiểm thử client truststore khi issuer thay đổi.

**Đạt** khi không có giai đoạn nào hệ thống chỉ có chứng thư được ký bởi CA mà client chưa tin cậy.

## 23. Câu hỏi tự kiểm tra

1. Tại sao `renew` Vault token không kéo dài hạn X.509 `NotAfter`?
2. Vì sao `lease_duration` có thể không đại diện cho vòng đời leaf certificate PKI?
3. Vault role giới hạn được những yếu tố nào: domain, wildcard, IP SAN, TTL, key type, server/client usage?
4. Sau khi gọi `issueCertificate` lần hai, điều gì chứng minh đã cấp **một leaf mới**?
5. Vì sao chỉ so sánh `newNotAfter > oldNotAfter` có thể không chính xác khi hai lần issue rất gần nhau?
6. Tại sao cần kiểm tra DNS SAN thay vì chỉ subject Common Name?
7. `CertificateBundle.createKeyStore` và `SSLContext.init` có tự thay certificate của Tomcat đang chạy không?
8. Vì sao phải probe rồi mới promote TLS identity mới?
9. Khi nào chứng thư cũ có thể giữ như fallback, và khi nào tuyệt đối không được dùng lại?
10. Vì sao negative test 403 phải chạy bằng workload token chứ không phải root token của Vault dev?
11. Làm thế nào xác nhận TLS endpoint sau rotation đang sử dụng serial mới, kể cả sau load balancer?
12. Trong hệ thống nhiều pod cùng nhận certificate, cần giải quyết những tình huống concurrency hoặc thundering herd nào?

## 24. Tổng kết

Bài thực hành **“Cấp chứng thư thử nghiệm rồi thay thế khi sắp hết hạn”** kết nối Vault PKI, workload authentication, ACL, Java Spring Vault, X.509, TLS runtime và kiểm thử tích hợp thành một quy trình thống nhất.

Các mốc quan trọng là: **dựng CA/role test có giới hạn**, **cấp leaf bằng `VaultPkiOperations.issueCertificate`**, **đọc `NotAfter`/SAN/EKU/CA trust thật**, **phát hiện cửa sổ cần thay bằng `Clock`**, **cấp bundle mới**, rồi **stage → probe → promote** identity ở TLS endpoint. Chứng thư đã được cấp không tự gia hạn khi token/lease được gia hạn; TLS server cũng không tự reload chỉ vì `VaultTemplate` nhận bundle mới.

Nghiệm thu phải dựa vào **handshake thật nhìn thấy serial mới**, không chỉ API issue thành công. Cần giữ nguyên tắc ít quyền nhất, không log private key, kiểm soát lỗi/rollback/revocation và có kiểm thử âm tính để tránh biến một cơ chế tự động thành điểm mở rộng quyền hoặc sự cố TLS.

### Tài liệu tham khảo

- [Spring Vault — PKI qua VaultPkiOperations](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html#vault.vault-secret-engines.pki)
- [Spring Vault — VaultPkiOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultPkiOperations.html)
- [Spring Vault — VaultCertificateRequest API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultCertificateRequest.html)
- [Spring Vault — CertificateBundle API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/CertificateBundle.html)
- [Spring Vault — VaultCertificateResponse API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultCertificateResponse.html)
- [HashiCorp Vault — PKI secrets engine API](https://developer.hashicorp.com/vault/api-docs/secret/pki)
- [HashiCorp Vault — Quick start root CA](https://developer.hashicorp.com/vault/docs/secrets/pki/quick-start-root-ca)
- [HashiCorp Vault — PKI considerations](https://developer.hashicorp.com/vault/docs/secrets/pki/considerations)
- [HashiCorp Vault — PKI rotation primitives](https://developer.hashicorp.com/vault/docs/secrets/pki/rotation-primitives)
