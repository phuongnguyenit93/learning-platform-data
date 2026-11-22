# Giám sát thời hạn chứng thư, metadata và keytab

> **Module:** Spring Security – federation · **Chủ đề cha:** Triển khai và vận hành. Bài Knowledge trình bày cách xây hệ thống theo dõi vòng đời các vật liệu tin cậy trong liên kết danh tính: **chứng thư X.509 của IdP/SP và HTTPS**, **SAML2 metadata** cùng giới hạn làm mới/hiệu lực, và **Kerberos keytab** chứa khóa bí mật của service principal. Mục tiêu không chỉ là báo “sắp hết hạn” mà còn bảo đảm cấu hình đang chạy thực sự sử dụng bộ khóa đúng, thay khóa có chồng lấn, có kiểm thử end-to-end và có runbook khôi phục **không tắt kiểm chứng chữ ký, không chấp nhận vé giả**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt X.509 `notBefore/notAfter`, SAML metadata `validUntil/cacheDuration`, thời hạn Kerberos ticket/TGT, tuổi khóa và **keytab không có trường “ngày hết hạn” giống certificate**.
2. Kiểm kê các chứng thư khác nhau: IdP signing/verification, SP signing, SP decryption, HTTPS/TLS leaf/chain và certificate của metadata-signing authority.
3. Hiểu sự khác nhau giữa **SAML explicit-key trust** qua metadata/registration và **PKIX certificate path validation**; không tuyên bố mặc định Spring Security tự reject mọi X.509 cert hết hạn hoặc tự kiểm tra OCSP/CRL.
4. Giải thích SAML metadata `validUntil` là giới hạn hiệu lực và `cacheDuration` là chính sách caching/refresh, kể cả attribute ở phần tử cha/nested EntityDescriptor và metadata đã stale nhưng chưa invalid.
5. Phân biệt ngày metadata được tải xuống với ngày **RelyingPartyRegistration đang có hiệu lực được thay thế**; kiểm soát HTTP/ETag/cache, chữ ký, issuer, endpoint và trust anchors.
6. Giám sát keytab bằng principal/realm/SPN, KVNO, encryption types, file permissions/ownership, trạng thái đồng bộ KDC và một phép thử GSS/`kvno -k` trong môi trường được phép.
7. Hiểu tại sao `klist -k -t` chỉ hiển thị timestamp của entry, không phải ngày khóa Kerberos sẽ “hết hạn”; và vì sao `klist -K` không được đưa vào log.
8. Thiết kế chỉ số, ngưỡng 90/60/30/14/7/1 ngày, cảnh báo freshness/trust, owner escalation, multi-replica rollout và tình huống đã quá hạn.
9. Thực hiện rollover SAML với overlap **old+new verification keys**, cập nhật SP/IdP metadata có ký và kiểm chứng; xử lý SP decryption key cũ cho ciphertext chưa xử lý.
10. Thực hiện Kerberos key rotation không gây mất dịch vụ, hiểu `kvno` mismatch, KDC-issued tickets còn sử dụng old keys và sự nguy hiểm khi quản trị viên chạy `ktadd` bất cẩn.
11. Xây một chương trình Java 17 chạy độc lập để đánh giá trạng thái certificate/metadata/keytab với stdout xác định; dùng JDK `CertificateFactory` để inspect cert thật.
12. Dùng Spring Boot Actuator/`HealthIndicator` cùng scheduled monitor thích hợp: không đặt network fetch nặng vào liveness probe, không để trang health công khai tiết lộ keys.
13. Xây bảng ma trận kiểm thử, tập signed SAML fixture/valid Kerberos tickets, tình huống network failure, certificate expiry, clock skew, wrong SPN, metadata replay và rollout rollback.
14. Viết runbook phát hiện, phân loại và phục hồi khi SAML/Kerberos SSO thất bại mà không giảm chuẩn xác thực.

**Nền tảng:** Java 17, Spring Boot 3.3.x/Spring Security 6.3.x để minh họa; khi production phải chọn version đang được hỗ trợ và rà soát API tương ứng. Lệnh `openssl`, `keytool`, MIT `klist`/`kvno` là công cụ điều tra tùy môi trường và quyền; không tự thay đổi KDC hay khóa thật. Các domain `example.org` và ngày trong bài là ví dụ, không phải cấu hình thực của tổ chức.

## 2. Ba loại tài sản, ba kiểu “hết hạn” khác nhau

| Tài sản | Trạng thái thời gian cần giám sát | Tín hiệu vận hành khác | Sai lầm thường gặp |
| --- | --- | --- | --- |
| X.509 IdP signing/verification | `notBefore`, `notAfter`; thêm lifecycle theo CA/trust contract. | SHA-256 fingerprint, key usage/algorithm, source metadata, overlap/revocation. | “Cert còn hạn ⇒ SAML signature chắc chắn hợp lệ”. |
| X.509 SP signing | Ngày hiệu lực, thời điểm đối tác ngừng tin khóa. | Private key tương ứng, IdP biết public cert, signed AuthnRequest canary. | Thay cert ở SP mà IdP chưa import. |
| X.509 SP decryption | Ngày hiệu lực và khả năng decrypt theo policy. | Private key đọc được, ciphertext còn dùng khóa cũ. | Xóa old decryption key ngay khi cấp cert mới. |
| HTTPS/TLS certificate | Leaf/chain notAfter, SAN hostname, key usage, CA path, OCSP/CRL theo TLS policy. | Host, reverse proxy, client TLS handshake. | Nghĩ TLS cert với SAML signing cert là một. |
| Metadata SAML của IdP/SP | `validUntil`; `cacheDuration`; lần fetch/validate/reload thành công. | XML signature trust, EntityID, ACS/SSO/SLO endpoints, KeyDescriptors, key overlap. | Coi cacheDuration hết là metadata **bị vô hiệu** như validUntil. |
| Kerberos keytab | **Không có X.509 notAfter** cho các keys trong keytab. | Service principal/realm, KVNO, enctype, file permissions, KDC agreement, successful ticket decryption. | Lấy keytab entry timestamp hoặc tuổi file làm ngày hết hạn. |
| Kerberos TGT/service ticket | Ticket `starttime/endtime/renew-till` nếu có. | KDC availability, clock skew, realm/SPN, service acceptor result. | Nhầm ticket expiry với keytab expiry. |

**Kết luận:** một dashboard chỉ lấy `notAfter` của một file PEM không đủ để bảo vệ hệ thống federation. Cần inventory quan hệ **ai phát khóa → ai sử dụng → nguồn nào công bố → tiến trình nào đang nạp → khi nào đối tác sẽ đổi**.

### 2.1. Sơ đồ chuỗi tin cậy

~~~text
                      Approved IdP
                      /      |      \
           IdP metadata   Signed SAML   HTTPS endpoint
           <KeyDescriptor> Assertion     TLS certificate
                 |            |               |
                 v            v               v
             SP trust      SP verifies    Browser/proxy TLS
             repository    SAML signature  trust path
                 |
             registration reload/rollover
                 |
               SP Session

              KDC/AD realm
                   |
            Kerberos service key
              (principal, kvno)
                   |
        +----------+------------+
        |                       |
   Keytab on node A        Keytab on node B
        |                       |
        +-- GSS accept service tickets
~~~

Cấu hình nào thuộc IdP, cái nào thuộc SP và cái nào thuộc Kerberos phải được ghi rõ. Chứng thư IdP có thể không dùng để bảo vệ HTTPS của IdP. Keytab không dùng chứng thư X.509 để giải mã Kerberos tickets thông thường.

## 3. Inventory: thiết kế nguồn sự thật trước khi đặt alert

Một record quản trị nên có:

| Thuộc tính | Ví dụ/ý nghĩa |
| --- | --- |
| `asset_id` | ID nội bộ ổn định, không chứa secret. |
| `asset_type` | `SAML_IDP_VERIFY`, `SAML_SP_SIGN`, `SAML_SP_DECRYPT`, `SAML_METADATA`, `TLS`, `KERBEROS_KEYTAB`. |
| `environment` | prod, staging, DR. |
| `registration_id` | `corp` trong Spring `RelyingPartyRegistrationRepository` hoặc IdP entity ID. |
| `owner_team` | IAM/Security/Platform/Partner owner và kênh escalation. |
| `dependency` | SP nodes, IdPs, gateway, clients, KDCs. |
| `trust_source` | Ký metadata, pin certificate, admin-approved file, PKIX policy. |
| `version_ref` | SHA-256 cert fingerprint, ETag/metadata digest, keytab KVNO; không export private key. |
| `validity` | `notBefore/notAfter` hoặc `validUntil/cacheDuration`, tùy loại. |
| `last_observed_at` | Thời gian UTC lần kiểm tra, xác nhận data fresh. |
| `last_refresh_success_at` | Lần metadata/registration refresh thành công. |
| `last_end_to_end_canary` | Lần signed SAML login hoặc Kerberos decrypt service-ticket test pass. |
| `next_rotation_at` | Ngày do chủ hệ thống phê duyệt, **không** tự suy từ keytab timestamp. |
| `change_id/runbook` | Ticket, kế hoạch rollout, rollback, đối tác và SLA. |

Mỗi asset có thể tồn tại thành **ba phiên bản**: phiên bản nguồn đang công bố, phiên bản được process nạp trong bộ nhớ và phiên bản đã triển khai trên các node. Đồng bộ ba phiên bản mới là nhiệm vụ vận hành thực sự.

### 3.1. Định nghĩa mốc thời gian

- `expires_at`: deadline hard validity nếu loại vật liệu thực sự có ngày hết hiệu lực.
- `refresh_due_at`: thời gian nên fetch/refresh, **không** mặc định là hard expiry.
- `rotation_due_at`: lịch quay khóa do tổ chức đặt, khác với expiry.
- `last_success_at`: lần canary/metadata load thành công; phải đo để phát hiện job âm thầm chết.
- `grace_overlap_end_at`: thời điểm được phép bỏ old key sau khi tất cả đối tác và in-flight artifacts đã chuyển.
- `criticality`: tier theo impact; hệ thống quan trọng cần cảnh báo sớm hơn.

## 4. X.509 trong federation: chứng thư nào đang được đo?

### 4.1. IdP signing/verification certificate

IdP ký SAML Response/Assertion bằng private key của IdP; SP kiểm chứng bằng **public key** được cấu hình làm trusted verification credential trong metadata hoặc registration đã được xác minh. Monitor cần:
- serial/issuer/subject/SAN (nếu có), public key algorithm và signature algorithm;
- `notBefore/notAfter` theo UTC;
- SHA-256 fingerprint để đối chiếu version, **không coi fingerprint là bí mật**;
- vị trí công bố trong IdP metadata `KeyDescriptor use="signing"` hoặc trường hợp `use` không khai báo theo SAML profile;
- danh sách **mọi** verification keys đang tin, không chỉ key đầu;
- thời điểm cập nhật metadata/sửa Spring registration đã deploy;
- signed-assertion canary thật với IdP test hoặc synthetic authorized login.

**Giới hạn cực quan trọng:** trong nhiều triển khai SAML, xác minh chữ ký sử dụng **explicit public key trust** dựa vào metadata/registration. Một certificate có `notAfter` đã qua **không bảo đảm** signature verification của mọi SP sẽ tự từ chối nó, nếu pipeline chỉ kiểm chữ ký bằng key chứ không chạy PKIX validity check. Ngược lại, certificate còn hạn cũng không chứng minh metadata/trust/issuer/audience hợp lệ. Chính sách kiểm tra X.509 dates, PKIX path, revocation CRL/OCSP cần được thiết kế/triển khai riêng và kiểm chứng trên **Spring Security/OpenSAML version thật**.

### 4.2. SP signing certificate

SP có thể dùng private key để ký AuthnRequest/LogoutRequest, công bố public certificate trong SP metadata cho IdP. Cần giám sát:
- chứng thư đang ký trên **từng node**, private key load được không;
- IdP hiện tin fingerprint cũ/mới nào và deadline đổi;
- AuthnRequest thật có ký nếu đối tác yêu cầu;
- SP metadata công bố certificate đúng;
- key rotation có overlap, không đổi private key/alias tùy tiện chỉ trên một node;
- permission của keystore/secret và source Vault.

### 4.3. SP decryption certificate

IdP có thể encrypt Assertions/NameID bằng SP public encryption certificate; SP dùng private key để decrypt. Khi thay:
1. Công bố **new public encryption key** cho IdP; xác nhận đối tác đã cập nhật.
2. Bắt đầu nhận ciphertext được mã hóa cho new key.
3. Giữ **old private key** chỉ trong khoảng chuyển tiếp cần thiết cho response còn trên đường/in-flight.
4. Ghi nhận last successful decrypt theo key version.
5. Sau cửa sổ chuyển đổi và xác nhận không còn phụ thuộc, retire old private key bằng cơ chế được duyệt.

Xóa old decryption key sớm có thể khiến Response vẫn được ký hợp lệ nhưng **không giải mã được**.

### 4.4. HTTPS TLS certificate là đường kiểm tra độc lập

Browser/HTTP client kiểm tra TLS chain, hostname, SAN, expiry và revocation theo policy; SAML signature kiểm tra XML signature/trust ở tầng ứng dụng. TLS certificate trên ingress proxy có thể hết hạn dù IdP signing cert còn hạn. Cần cảnh báo hai tuyến riêng, kể cả chain intermediates và reverse proxy đang thực sự phục vụ certificate nào.

### 4.5. Kiểm tra tại máy với OpenSSL/JDK

~~~bash
# Kiểm tra public certificate; không chứa private key.
openssl x509 \
  -in /etc/federation/idp-signing.pem \
  -noout -dates -subject -issuer -serial -fingerprint -sha256

# Một public cert của SP dùng ký AuthnRequest.
openssl x509 \
  -in /etc/federation/sp-signing.pem \
  -noout -dates -fingerprint -sha256

# Java tool cũng có thể hiển thị hạn chứng thư.
keytool -printcert -file /etc/federation/sp-signing.pem

# TLS live endpoint: kiểm tra certificate thực tế từ proxy.
# Sử dụng tool TLS đã được approve; không tắt hostname verification.
~~~

Phải so với **certificate đang chạy**, không chỉ file trên disk. Một bản PEM mới copy vào image/volume nhưng Java process chưa reload có thể làm dashboard dựa file báo OK trong khi SP vẫn tin certificate cũ.

**Không** kiểm tra bằng cách in private key, `openssl pkey -text` lên console/CI, hoặc paste truststore/keytab vào ticket hỗ trợ.

## 5. Giám sát certificate bằng Java 17

Java standard API `CertificateFactory` và `X509Certificate` có thể đọc public cert và kiểm tra `getNotBefore()/getNotAfter()`, `checkValidity()`. Ví dụ đầy đủ sau đọc file certificate PEM/DER, hiển thị ngày và ngưỡng cảnh báo **không đọc private key**.

### 5.1. `X509ExpiryAudit.java`

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

public final class X509ExpiryAudit {

    enum Status { OK, WARN, CRITICAL }

    static Status evaluate(
            X509Certificate cert, Instant now, int warnDays) {
        Instant notBefore = cert.getNotBefore().toInstant();
        Instant notAfter = cert.getNotAfter().toInstant();

        if (now.isBefore(notBefore) || now.isAfter(notAfter)) {
            return Status.CRITICAL;
        }
        if (!now.plus(Duration.ofDays(warnDays))
                .isBefore(notAfter)) {
            return Status.WARN;
        }
        return Status.OK;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                "Usage: java X509ExpiryAudit <public-cert.pem>");
            System.exit(2);
        }

        Path path = Path.of(args[0]);
        try (InputStream in = Files.newInputStream(path)) {
            X509Certificate cert = (X509Certificate)
                CertificateFactory.getInstance("X.509")
                    .generateCertificate(in);

            Instant now = Clock.systemUTC().instant();
            long daysLeft = Math.floorDiv(
                Duration.between(now,
                    cert.getNotAfter().toInstant()).getSeconds(),
                86_400
            );

            System.out.println("notBefore=" +
                cert.getNotBefore().toInstant());
            System.out.println("notAfter=" +
                cert.getNotAfter().toInstant());
            System.out.println("daysLeftFloor=" + daysLeft);
            System.out.println("status=" +
                evaluate(cert, now, 30));

            // Phân biệt: checkValidity chỉ kiểm tra thời gian.
            try {
                cert.checkValidity(Date.from(now));
                System.out.println("x509TimeValidity=PASS");
            } catch (java.security.cert.CertificateException e) {
                System.out.println("x509TimeValidity=FAIL");
            }
        }
    }
}
~~~

### 5.2. Chạy

~~~bash
javac --release 17 X509ExpiryAudit.java
java X509ExpiryAudit /etc/federation/idp-signing.pem
~~~

Output thay đổi theo **chứng thư thực và thời gian hiện tại**, nên không đưa một stdout giả định là “kết quả chắc chắn”. Ví dụ minh họa (không phải output đã thực thi):

~~~text
notBefore=2026-01-01T00:00:00Z
notAfter=2027-01-01T00:00:00Z
daysLeftFloor=<derived-from-current-time>
status=OK
x509TimeValidity=PASS
~~~

**Giới hạn:** Mẫu chỉ đọc **một** public certificate. Nó **không** kiểm tra PKIX chain, CRL/OCSP, issuer trust, public/private key pairing, certificate usage, SAML metadata signature hoặc runtime Spring registration. Production cần kiểm tra toàn bộ các certificate entries/chain/key versions trong từng registration/keystore và monitor thực tế từ runtime.

### 5.3. NotBefore cũng gây sự cố

Một cert được phát có `notBefore` trong tương lai hoặc nodes bị lệch đồng hồ có thể không được PKIX validator tin theo thời gian hệ thống. `notAfter` còn lâu không đủ để kết luận valid. Monitor cần trạng thái:
- `NOT_YET_VALID` nếu now < notBefore;
- `EXPIRING_SOON` nếu trong cảnh báo;
- `EXPIRED` nếu sau notAfter;
- `TRUST_NOT_VERIFIED` nếu chỉ đọc file mà chưa có PKIX/metadata trust validation;
- `KEY_MISMATCH` nếu private key/cert public key không khớp;
- `RUNTIME_STALE` nếu process vẫn dùng certificate cũ.

Không in raw key material, chỉ fingerprint/cert public metadata và kết quả canary.

## 6. SAML metadata: validUntil khác cacheDuration

Đây là một trong các lỗi triển khai phổ biến nhất.

### 6.1. `validUntil`

Trong SAML metadata, `validUntil` xác định thời điểm metadata instance **không còn hợp lệ**. OASIS Errata 05 nêu rõ metadata phải được coi là invalid khi tới `validUntil`, và phần tử cha có thời hạn sớm hơn có thể làm effective expiration ngắn hơn.

Ví dụ:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml"
    validUntil="2026-12-31T00:00:00Z">
  <!-- IDPSSODescriptor, KeyDescriptor, SSO endpoints ... -->
</md:EntityDescriptor>
~~~

**Nếu effective `validUntil` đã qua**, không dùng metadata instance đó làm nguồn trust hợp lệ chỉ vì HTTP 200 hoặc cache vẫn có XML. Cần fetch/validate metadata mới và hành động theo chính sách fail-closed.

Nếu metadata chứa `EntitiesDescriptor` cha:

~~~xml
<md:EntitiesDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    validUntil="2026-11-20T00:00:00Z">
  <md:EntityDescriptor
      entityID="https://idp.example.org/saml"
      validUntil="2026-12-31T00:00:00Z">
      <!-- ... -->
  </md:EntityDescriptor>
</md:EntitiesDescriptor>
~~~

Với IdP nằm bên trong, effective deadline không được tự lấy 31/12 nếu phần tử cha hết hạn 20/11. Trong công cụ kiểm tra cần duyệt hierarchy và chọn hạn hiệu lực phù hợp (thường deadline sớm nhất được áp dụng).

### 6.2. `cacheDuration`

`cacheDuration` chỉ **khoảng thời gian tối đa nên giữ metadata trong cache trước khi thử refresh** (với parent precedence theo profile), không nhất thiết nói metadata invalid khi cache tuổi quá lâu. Theo OASIS Errata E94, metadata vượt khoảng cacheDuration là **stale**; có thể còn hợp lệ nếu không vượt `validUntil` và policy cho phép sử dụng tạm khi network refresh lỗi.

Ví dụ:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml"
    cacheDuration="PT6H"
    validUntil="2026-12-31T00:00:00Z">
  <!-- ... -->
</md:EntityDescriptor>
~~~

Nếu tải lúc 08:00 UTC, cần thử refresh theo cacheDuration khoảng 14:00 UTC. Khi 15:00 chưa refresh:
- **`CACHE_STALE`**: cần cảnh báo và retry;
- **không tự suy `METADATA_INVALID`** nếu effective validUntil còn xa;
- **không vô hạn dùng metadata cũ**: định nghĩa giới hạn stale tối đa theo rủi ro và trạng thái trust;
- nếu validUntil thực sự đã qua → **invalid**, không sử dụng như một cấu hình tin cậy còn hợp lệ.

**Hai mặt khác nhau:** metadata cache freshness giúp thay đổi kịp khi IdP revoke/rollover keys; metadata validity là giới hạn hiệu lực cứng.

### 6.3. Nếu không có `validUntil` hoặc `cacheDuration`

Không suy metadata vĩnh viễn đáng tin. Tổ chức nên có:
- local maximum metadata age;
- bắt buộc signed metadata nếu nguồn/kênh không tin cậy;
- expiry/refresh cadence theo hợp đồng với IdP;
- manual approval/trust pinning cho static metadata;
- alert thiếu `validUntil` khi policy yêu cầu;
- kiểm tra kết quả refresh và runtime reload;
- fallback/cutover đã duyệt, không tự tin metadata bất kỳ từ URL mới.

### 6.4. XML duration không phải “số ngày” luôn cố định

`cacheDuration` dùng xs:duration, có thể có ngày/giờ hoặc các thành phần khác tùy profile. Hãy dùng parser XML Schema duration chính xác theo ngữ cảnh **thời điểm metadata fetch**, tránh tự parse bằng regex lấy số trước chữ `D` rồi bỏ qua months/timezones. Clock NTP/UTC đồng bộ cho nguồn và consumers.

### 6.5. Bảng trạng thái metadata

| Tình huống | Trạng thái monitor | Hành động |
| --- | --- | --- |
| Signature/trust không hợp lệ | `UNTRUSTED`/CRITICAL | Không promote, điều tra nguồn/keys. |
| EntityID/SSO endpoint bất ngờ đổi | `DRIFT_REVIEW` | Chặn tự động promote theo policy, đối chiếu change ticket. |
| effective validUntil đã qua | `INVALID_EXPIRED`/CRITICAL | Không sử dụng metadata hết hiệu lực; khôi phục nguồn tin hợp lệ. |
| CacheDuration hết, validUntil còn | `STALE_REFRESH_DUE`/WARN | Retry refresh và cảnh báo theo SLA. |
| HTTP fetch 200, XML parse fail | `FETCHED_NOT_VALIDATED` | Không thay good snapshot bằng XML lỗi. |
| HTTP 304 Not Modified và cache còn hợp lệ | `UNCHANGED` | Xác minh/cache semantics đúng; đừng cộng vô hạn tuổi trust ngoài policy. |
| Metadata mới trusted, runtime vẫn dùng key cũ | `RUNTIME_STALE`/CRITICAL tùy deadline | Reload registration, test SAML canary. |
| Metadata mới có old+new keys | `ROLLOVER_OVERLAP` | Theo dõi hai fingerprint và xác minh signed fixture cho cả hai. |
| Không có validUntil | `LOCAL_MAX_AGE_POLICY` | Áp hạn do tổ chức định nghĩa; không coi never-expire. |

## 7. Metadata trust: tải được không đồng nghĩa tin được

Một URL metadata trả HTTP 200 chỉ chứng minh server đã trả bytes. Trước khi đưa vào `RelyingPartyRegistration`, cần:
1. Lấy metadata từ **source URL allowlisted** và HTTPS/pinned trust khi phù hợp, không lấy `metadataUrl` từ browser query.
2. Validate XML parser chống XXE/DTD/entity expansion, giới hạn kích thước và timeout.
3. Khi yêu cầu signed metadata: xác minh XML signature bằng **metadata signing trust anchor đã được phê duyệt ngoài metadata mới**, không tự tin key tự công bố trong chính file chưa được kiểm tra.
4. Chọn đúng EntityDescriptor/EntityID, IDPSSODescriptor/SPSSODescriptor, SSO/SLO endpoints, supported bindings và KeyDescriptors.
5. Đánh giá effective `validUntil/cacheDuration`, signer/endpoint/key changes và policy.
6. Validate certificate types/algorithms và rollover keys theo security contract.
7. Stage phiên bản mới, thử ký/xác minh SAML Response/AuthnRequest, kiểm tra logout/decrypt nếu dùng.
8. Promote atomically cho toàn cụm hoặc có chiến lược chuyển tiếp; chỉ khi thành công cập nhật `last_applied_at`.
9. Giữ backup metadata/certificate **đã tin cậy và chưa hết hiệu lực** theo policy để rollback, không dùng XML signed nhưng expired.
10. Audit source fingerprint/metadata digest, ETAG và lý do accept/reject, không log toàn bộ assertions.

**Lưu ý:** TLS bảo vệ vận chuyển nhưng không thay thế trust policy khi metadata được lấy từ kênh có thể bị đổi, hoặc khi yêu cầu signed metadata. Signed XML không tự cho phép tin mọi signer; trust anchor phải được quản trị.

### 7.1. Phân biệt source / cache / runtime

~~~text
IdP metadata endpoint
       |
       | fetch, TLS, signed metadata verification
       v
Approved snapshot (digest, validUntil, key set)
       |
       | cacheDuration/refresh policy
       v
RelyingPartyRegistration repository
       |
       | actual reload / cache invalidation
       v
Spring Security runtime verification credentials
       |
       | signed SAML login canary
       v
Observed authentication behavior
~~~

Cần monitor từng mũi tên. Nếu chỉ có `metadata_http_status=200` nhưng registry vẫn giữ bản cũ do load-once repository, signed Assertion khi IdP rotate key sẽ fail.

## 8. Spring Security: quản lý runtime RelyingPartyRegistration

Spring Security hỗ trợ SP dựa `RelyingPartyRegistrationRepository`. Một registration chứa SP EntityID/ACS, IdP EntityID/SSO và các signing/decryption/verification credentials.

### 8.1. Spring Boot YAML tĩnh

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              entity-id: "https://idp.example.org/saml"
              singlesignon:
                url: "https://idp.example.org/sso"
              verification:
                credentials:
                  - certificate-location: "file:/etc/federation/idp-sign-current.pem"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/etc/federation/sp-signing.pem"
~~~

**YAML minh họa phải đối chiếu property schema đúng phiên bản Boot đang dùng.** Điểm cốt lõi: certificate từ IdP dùng xác minh, private key SP dùng ký/decrypt phải được quản trị riêng. Nếu file được thay trên disk, **đừng giả định** các `RelyingPartyRegistration` đã tạo trong memory tự reload. Phải kiểm tra lifecycle của config/repository hoặc rollout ứng dụng theo kế hoạch.

**Không thêm đường dẫn private key vào health response, logs, dashboards hoặc exported actuator details.**

### 8.2. Metadata URL load-once và refresh

Spring có tiện ích `RelyingPartyRegistrations.fromMetadataLocation(...)` để tạo registration từ metadata. Điều đó **không đồng nghĩa** mỗi request đều fetch metadata mới. Tùy phiên bản/config, `InMemoryRelyingPartyRegistrationRepository` là snapshot trong memory. Với Spring Security đời mới, tài liệu mô tả `CachingRelyingPartyRegistrationRepository` và cơ chế refresh theo cache eviction schedule; version cũ có thể không có API này/khác hành vi.

**Khi thiết kế refresh**, không chỉ đặt cron `fetch every hour` mà cần:
- validate trusted XML/keys trước khi thay cấu hình;
- đảm bảo cache eviction thực sự gọi lại loader;
- đo `last_refresh_success_at` và `last_registration_applied_at`;
- theo dõi ở **từng replica**, không chỉ một node;
- phân biệt HTTP 304, fetch fail, parse fail, signature fail, no-change;
- có giới hạn staleness, backoff/jitter và alert;
- kiểm tra signed login canary qua ACS sau reload;
- bảo đảm không thay registration bằng dữ liệu sai EntityID/issuer.

### 8.3. SP metadata công bố ra ngoài

Spring Security có `saml2Metadata(...)` để phát SP metadata (endpoint tùy version, thường `/saml2/metadata` hoặc path có registrationId). Monitor phải kiểm tra:
- public `entityId` đúng;
- ACS URL đúng public HTTPS hostname/port sau reverse proxy;
- signing/encryption certificates công bố khớp runtime;
- SP metadata endpoint còn hoạt động;
- IdP partner đã import/đồng bộ phiên bản mới;
- XML không bị reverse proxy cache quá lâu;
- metadata ký hay unsigned theo trust contract với partner.

Một SP metadata endpoint trả 200 không chứng minh partner đã tin certificate mới. Phải có bên nhận xác nhận hoặc signed AuthnRequest/SAML Response end-to-end test.

### 8.4. Explicit-key trust và PKIX

Giám sát `notAfter` có giá trị vận hành, nhưng nếu Spring/OpenSAML được cấu hình xác minh SAML signature bằng trusted key, **certificate validity check có thể không nằm trên cùng đường xác minh** như TLS/PKIX. Không kết luận “cert hết hạn => login chắc chắn fail” hoặc “login vẫn pass => cert chưa hết hạn”. Đọc version-specific validator implementation, thiết kế policy kiểm tra certificate dates/revocation và test các kịch bản expired/not-yet-valid/untrusted key thật.

### 8.5. Certificate rollover old/new

~~~text
T-60d:  inventory old key fingerprint + expiry/owner
T-30d:  IdP phát metadata đã được ký có old+new certs
T-14d:  SP validate metadata và trust cả old+new, tests pass
T-7d:   IdP bắt đầu ký bằng new key (được phối hợp)
T+0:    monitor confirms all SP nodes accept new signatures
T+N:    retire old key sau overlap & delayed messages hết hạn
~~~

Các mốc chỉ minh họa; thay đổi theo thời hạn/lifecycle thật của vendor. Nếu IdP không hỗ trợ double KeyDescriptor, phải có migration/cutover window rõ với rollback. Không xóa old key chỉ vì new cert đã được tải xuống nhưng chưa có canary xác minh.

## 9. Kerberos keytab: không có notAfter kiểu X.509

**Keytab là file chứa khóa bí mật cho Kerberos principal** (thường SPN `HTTP/portal.example.org@EXAMPLE.ORG`), có thể nhiều key entries theo KVNO/encryption type. Khi browser lấy service ticket từ KDC, ứng dụng acceptor/GSS-API phải có khóa tương ứng để giải mã/xác minh ticket.

### 9.1. Phân biệt các mốc

| Khái niệm | Có thời hạn? | Phương pháp kiểm tra |
| --- | --- | --- |
| Keytab entry | Không có field notAfter tương tự certificate. | Principal, realm, KVNO, enctype, access/rotation status. |
| Keytab entry timestamp | Thường là thời điểm record được tạo/ghi vào keytab; **không là expiry**. | `klist -k -t` chỉ để quan sát metadata. |
| KDC principal key | Có lifecycle/rotation/KVNO theo quản trị; chính sách có thể áp key lifetime. | KDC authoritative admin view hoặc approved monitoring API. |
| Service ticket | Có start/endtime; vé hết hạn và KDC policy. | `klist` credentials cache, test SPNEGO/GSS. |
| TGT | Có lifetime/renew-till. | `klist` ticket cache; không suy file keytab hết hạn. |
| Password/account/service principal disabled | Có thể khóa/xóa/revoke theo AD/KDC policy. | Directory/KDC authoritative status + canary. |

Một file keytab còn “mới” vẫn có thể sai `KVNO` hoặc wrong SPN. Một file keytab cũ về mtime vẫn có thể chứa key đúng nếu KDC chưa đổi. **Ngày sửa file không thay phép thử decryption**.

### 9.2. Những gì phải giám sát

- `principal` và realm trong keytab khớp service hostname/Kerberos SPN mà clients thực sự yêu cầu.
- `KVNO` entries trong keytab tương thích key version KDC có thể phát và các tickets còn tồn tại.
- Encryption types (enctypes) phù hợp chính sách KDC/service/JDK, không ép legacy DES/RC4 để “sửa nhanh”.
- File tồn tại, readable chỉ bởi service account được cấp quyền, không world-readable.
- Ownership và secret distribution giữa nodes A/B, hash/manifest version đã quản trị (hash keytab cần bảo vệ như dữ liệu nhạy cảm, không đưa công khai).
- Config `krb5.conf`, DNS SRV, SPN registration, KDC reachability và time synchronization.
- Canary có **TGT/test principal được phép** lấy service ticket và thử giải mã bằng keytab/acceptor, không in ticket/key.
- Cảnh báo khi KDC KVNO đổi nhưng chưa rollout keytab; ghi rõ overlap version supported.
- Keytab rotation change ticket và owner acknowledgement; **không tự suy deadline từ tuổi file**.

### 9.3. Lệnh MIT Kerberos không lộ khóa

~~~bash
# Liệt kê principal/KVNO; -e hiển thị enctype.
klist -k -e /run/secrets/http-service.keytab

# -t hiển thị entry timestamps (KHÔNG phải expiry).
klist -k -t /run/secrets/http-service.keytab

# Khi có KDC network và client TGT được phép:
# -k thử giải mã service ticket bằng keytab local.
kvno -k /run/secrets/http-service.keytab \
  HTTP/portal.example.org@EXAMPLE.ORG

# Chỉ với credential cache kiểm thử:
klist
~~~

**Cấm log `klist -K`:** MIT Kerberos document rõ option `-K` hiển thị **giá trị encryption keys** trong keytab. Không dùng nó trong monitor, CI, ticket hoặc terminal sharing. Không đính kèm file keytab vào bug report.

`kvno -k` là một test hữu ích nhưng cần một credential cache/TGT hợp lệ, KDC hoạt động và service ticket đúng; **chạy thất bại không tự chứng minh keytab bị hỏng** nếu DNS, clock, network hoặc client credential fail. Tách nguyên nhân theo diagnostics, không “sửa” bằng cách tắt ticket validation.

### 9.4. Keytab/KVNO drift

Ví dụ:

~~~text
KDC principal: HTTP/portal.example.org@EXAMPLE.ORG
KDC issues tickets with KVNO=7

Node-A keytab:
  principal correct
  enctypes supported
  KVNO=7
  ticket decryption PASS

Node-B keytab:
  principal correct
  only KVNO=6
  ticket decryption FAIL

Effect:
  Some login requests work on Node-A but fail on Node-B,
  creating intermittent 401 Negotiate / GSS failures.
~~~

Một số deployments giữ old keys/tickets trong overlap, nên **KVNO mismatch không luôn đồng nghĩa down ngay**. Quan trọng nhất là **KDC issuing behavior + acceptor canary + rotation policy**, không chỉ so số một cách máy móc. Hãy test từng node và ticket versions.

### 9.5. Cảnh báo khi dùng kadmin/ktadd

MIT Kerberos `kadmin ktadd` có thể **randomize principal keys** theo mặc định khi trích xuất keytab, làm tăng KVNO và khiến các service nodes chưa được cấp key mới thất bại. Việc “chạy lại ktadd để lấy keytab mới” **không phải** thao tác chỉ đọc.

Quy trình an toàn:
1. Lên change ticket, xác định realm/KDC implementation (MIT/AD), quyền admin và cách rotation phù hợp.
2. Tạo/cấp keytab theo cơ chế được phê duyệt cho KDC đó; hiểu liệu command có đổi principal password/keys và KVNO hay không.
3. Cấp keytab mới qua Vault/secret manager, file permissions chặt chẽ, không gửi qua email/chat.
4. Rollout có overlap/rolling restart theo cách KDC cho phép, kiểm tra tickets cũ và mới.
5. Theo dõi `klist -k -e` trên từng node và canary `kvno -k`/GSS acceptor.
6. Khi đã thành công và không còn cần old keys, retire old secrets bằng quy trình được duyệt.
7. Đảm bảo rollback thực tế: quay về old keytab **không** luôn khôi phục nếu KDC đã thay key và xóa old KVNO; cần KDC/AD admin phối hợp.

**Không** tự chạy `ktadd`, `cpw -randkey` hoặc thay password principal trong monitor job. Monitor là read-only; rotation phải là controlled action.

## 10. Giám sát Kerberos qua Spring Security và GSS

Spring Security Kerberos thường được cung cấp qua **Spring Security Kerberos extension** riêng với provider/filter, không nằm sẵn trong starter `spring-boot-starter-security`. Khi tích hợp Boot 3.x/Jakarta Servlet phải xác nhận compatibility/version thực tế.

Các thành phần thường gặp:
- `SpnegoAuthenticationProcessingFilter` nhận `Authorization: Negotiate`;
- `KerberosServiceAuthenticationProvider`/`SunJaasKerberosTicketValidator` xác minh service ticket dùng keytab;
- `SpnegoEntryPoint` phát `WWW-Authenticate: Negotiate`;
- GSS-API/JAAS và `krb5.conf`, SPN, KDC.

Monitor cần cả:
- **control plane:** file/keytab/KDC metadata, KVNO, enctypes, NTP;
- **data plane:** một browser/service client được phê duyệt thật sự lấy ticket và SPNEGO accept thành công;
- **local authorization:** user principal được link đúng local account và policy, không grant role chỉ vì ticket được accept.

Tránh coi một response `401 WWW-Authenticate: Negotiate` là lỗi Kerberos: đó có thể chỉ là **challenge ban đầu hợp lệ**. Lỗi nằm ở challenge-response không thành công, vé sai, keytab/clock mismatch hoặc account bị chặn.

### 10.1. Lỗi cần phân biệt

| Dấu hiệu | Khả năng | Kiểm tra |
| --- | --- | --- |
| `KRB_AP_ERR_MODIFIED` | SPN duplicate, wrong key, wrong KVNO, service ticket decrypt fail. | SPN/KDC keytab entries, kvno canary, node correlation. |
| `Clock skew too great` | NTP/time lệch. | UTC/NTP offset, ticket start/end, KDC time. |
| `Server not found in Kerberos database` | SPN/realm/DNS sai. | Service principal registration, DNS, realm mapping. |
| `No credentials provided` | Client browser chưa có ticket/TGT hoặc không hỗ trợ. | Browser/KDC flow; không tự kết luận keytab lỗi. |
| GSS accept fail chỉ trên một replica | Keytab/JAAS config/permissions drift. | Per-node versions/ACL/rollout state. |
| Kerberos ticket accept pass nhưng app 403 | Local role/tenant/account status. | Authorization audit, không sửa keytab bừa. |
| Keytab KVNO đổi nhưng canary vẫn pass | Overlap/old tickets được chấp nhận. | Theo dõi transition; cảnh báo WARN có owner. |
| Keytab file readable nhưng canary fail | Key sai/SPN/enctype/KDC/clock. | Triangulate client & KDC, không tắt checks. |

## 11. Kiến trúc giám sát vận hành

### 11.1. Agent và pipeline

~~~text
Cert/metadata monitor (read-only)
      |       |
      |       +--> parse X509 dates/fingerprints
      |       +--> validate signed metadata, validUntil,
      |            cacheDuration, source fetch, runtime digest
      |
Keytab monitor (privileged, read-only)
      |
      +--> minimal klist -k -e (no -K)
      +--> approved ticket-decrypt canary
      +--> principal/kvno/enctype/status from KDC API
      |
      v
       Normalized signals/metrics
                 |
                 v
       Alert rules + incident routing
                 |
      +----------+-----------+
      |                      |
    IAM/Security          Platform SRE
      |                      |
    IdP keys              Spring runtime,
    metadata              keytab nodes
      \                      /
       \-- change plan/rollover --/
                 |
             Staging canary
                 |
             Prod rollout + readback
~~~

Không để monitor tự thay đổi trusted SAML keys hoặc tự gọi KDC password reset. Nhiệm vụ monitor là **quan sát và báo động**. Việc promote trust material phải qua policy/change control đã phê duyệt.

### 11.2. Tần suất gợi ý

| Tài sản/kiểm tra | Chu kỳ tham khảo | Ghi chú |
| --- | --- | --- |
| X509 `notAfter` và fingerprint nguồn | Hằng ngày và khi config thay đổi. | Bắt đầu escalation trước hạn theo tier. |
| TLS endpoint live cert | Hằng giờ hoặc theo SLA. | Theo dõi ingress serving cert và chain. |
| Metadata HTTP fetch/refresh | Theo effective cacheDuration và backoff/jitter. | Không hard-code lịch lâu hơn provider contract. |
| Metadata effective validUntil | Hằng giờ hoặc mỗi refresh. | Cảnh báo trước hạn, fail closed khi invalid. |
| Applied metadata/runtime digest | Sau mỗi reload + định kỳ. | Phát hiện stale cache, rollout không đồng bộ. |
| Keytab `principal/KVNO/enctype` | Sau rotation + định kỳ. | Monitor là read-only. |
| Kerberos ticket acceptance canary | Theo SLA và trước/sau keytab rollover. | Dùng test principal được cấp phép, tránh brute-force. |
| Backup/DR key availability | Trong mỗi DR drill. | Quyền, secret sync và khả năng giải mã. |
| NTP offset/KDC health | Liên tục theo hạ tầng. | Clock skew làm sai cả SAML và Kerberos. |

**Tần suất không phải thông số mặc định framework.** Cần điều chỉnh cho metadata cache contract, độ quan trọng dịch vụ, hạn cert ngắn, key rotation cadence và operational capacity.

## 12. Ngưỡng cảnh báo và escalation

### 12.1. Mẫu rule theo deadline

| Còn tới deadline | Ví dụ mức cảnh báo | Người nhận/hành động |
| --- | --- | --- |
| 90 ngày | INFO / rotation backlog | Owner lên lịch với IdP/CA/KDC. |
| 60 ngày | WARN | Confirm người phối hợp và chứng thư/key mới. |
| 30 ngày | HIGH | Change ticket, staging test, quyết định rollout. |
| 14 ngày | HIGH / ESCALATE | Kiểm tra overlap, partner acknowledgement. |
| 7 ngày | CRITICAL pre-expiry | Phải có rollback/incident plan và trực SRE/IAM. |
| 1 ngày | PAGE | Incident commander và chủ hệ thống. |
| Đã quá deadline validity | CRITICAL | Fail closed với metadata invalid; khôi phục theo runbook. |

**Đây là chính sách ví dụ, không phải chuẩn bắt buộc.** Một IdP signing cert có `notAfter` 3 năm nhưng partner đổi signing key đột xuất hôm nay vẫn là incident; phải theo dõi **key drift / trust mismatch** cùng deadline. Keytab không áp “sắp hết hạn cert”: thay bằng `rotation_due_at` và canary fail/mismatch.

### 12.2. Có thể dùng Prometheus/Grafana

Metrics đề xuất, không tự có từ Spring Security:

~~~text
federation_cert_not_after_timestamp_seconds{asset_id,usage,env}
federation_cert_seconds_until_expiry{asset_id,usage,env}
federation_cert_validity_state{asset_id,state}
federation_metadata_valid_until_timestamp_seconds{registration_id}
federation_metadata_refresh_due_timestamp_seconds{registration_id}
federation_metadata_age_seconds{registration_id}
federation_metadata_refresh_success_timestamp_seconds{registration_id}
federation_metadata_applied_timestamp_seconds{registration_id,node_group}
federation_metadata_trust_valid{registration_id}
federation_metadata_runtime_digest_mismatch{registration_id,node_group}
federation_keytab_canary_success{service_id,node_group}
federation_keytab_kvno_mismatch{service_id,node_group}
federation_keytab_principal_expected{service_id,node_group}
federation_keytab_enctype_allowed{service_id,node_group}
federation_keytab_rotation_due_timestamp_seconds{service_id}
federation_saml_login_success_total{registration_id}
federation_saml_signature_error_total{registration_id,reason_class}
federation_kerberos_accept_error_total{service_id,reason_class}
~~~

Labels phải low-cardinality; không chứa nguyên username, raw `sub`/NameID, tokens, keytab contents, private key, certificate subject có PII, IP bất kỳ hoặc metadata URL do user nhập. `asset_id/service_id/registration_id` là định danh approved ổn định; policy giới hạn cardinality. Không xuất `keytab KVNO` dưới dạng cấu trúc chứa secret hay log mã hóa key.

### 12.3. Rule ví dụ

~~~yaml
groups:
  - name: federation-trust
    rules:
      - alert: FederationCertificateExpiring
        expr: federation_cert_seconds_until_expiry < 30 * 24 * 3600
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Federation certificate within 30 days of expiry"

      - alert: FederationMetadataInvalid
        expr: time() >= federation_metadata_valid_until_timestamp_seconds
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "SAML metadata validity expired"

      - alert: KerberosServiceTicketCanaryFailed
        expr: federation_keytab_canary_success == 0
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Kerberos service-ticket validation canary failed"
~~~

**Lưu ý metric semantics:** Không phát timestamp validity = 0 cho asset thiếu `validUntil`, nếu không rule “metadata expired” sẽ báo sai. Thiếu validUntil cần metric policy riêng; monitor không có fresh sample cũng phải có `up/absent`/last-success check. `federation_cert_seconds_until_expiry` âm nghĩa đã hết hạn, có thể tách rule critical. Không auto-rotate qua Prometheus alert.

## 13. Spring Boot Actuator/HealthIndicator: cảnh báo mà không lộ secret

`spring-boot-starter-actuator` cung cấp health/info/metrics; có thể viết custom `HealthIndicator` cho snapshot đã được monitor cập nhật. Không nên chạy XML fetch/KDC password/keytab decrypt nặng **mỗi lần Kubernetes gọi /actuator/health/liveness**. Liveness nhằm biết tiến trình có cần restart, không nên chết theo IdP network outage.

### 13.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Dự án Boot 3.x có SAML SP cần OpenSAML/Shibboleth artifacts theo dependency repositories/versions hiện hành. Cần xác minh BOM và JDK support của phiên bản deploy.

### 13.2. HealthIndicator mảnh minh họa

~~~java
// MẢNH SPRING BOOT: không phải file Java độc lập.
// FederationSnapshot do một scheduled monitor cập nhật theo policy.
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("federationTrust")
public final class FederationTrustHealthIndicator
        implements HealthIndicator {

    private final FederationSnapshot snapshot;

    public FederationTrustHealthIndicator(
            FederationSnapshot snapshot) {
        this.snapshot = snapshot;
    }

    @Override
    public Health health() {
        FederationStatus state = snapshot.status();
        if (state == FederationStatus.CRITICAL) {
            return Health.down()
                .withDetail("status", "critical")
                .build();
        }
        if (state == FederationStatus.WARN) {
            // Health UP ở đây không tự xóa cảnh báo metric.
            return Health.up()
                .withDetail("status", "renewal_due")
                .build();
        }
        return Health.up()
            .withDetail("status", "ok")
            .build();
    }
}
~~~

**Quan trọng:** `FederationSnapshot`/`FederationStatus` trong mảnh trên là **types của module monitor cần tự triển khai**, không được giả là Spring Boot built-ins. Chi tiết health không được chứa private key, keytab path có nhạy cảm, raw cert subjects hoặc XML metadata. Cần secure Actuator access và đặt `management.endpoint.health.show-details=never` hoặc `when-authorized` theo chính sách.

Nếu đưa warning “sắp hết cert” vào **readiness DOWN** ngay 30 ngày trước hạn, orchestrator có thể tự loại bỏ mọi replica dù chúng vẫn authenticate được → sự cố tự gây ra. Map **hard failure/cannot authenticate** vào readiness/incident theo risk policy; pre-expiry nên alert nhưng không nhất thiết restart/evict nodes.

### 13.3. Scheduled monitor, không phải request handler

~~~text
@Scheduled job / external collector
  -> inspect trusted certs/metadata + keytab canary
  -> update immutable snapshot + metrics + last_success
  -> Actuator read-only exposes summarized status
  -> AlertManager routes to correct owner
~~~

Job định kỳ phải có timeout, jitter/backoff, rate limit, secret access control và atomic snapshot; nếu không chạy được, xuất **UNKNOWN / monitoring gap** chứ không lặp lại OK vô hạn. Dù health báo UP, vẫn cần end-to-end signed SAML login/SPNEGO canary cho từng provider/node.

## 14. Java 17 chạy độc lập: policy monitor với stdout xác định

Ví dụ này không đọc private key và **không giả vờ xác minh SAML/Kerberos protocol**. Nó mô phỏng các bằng chứng đã được monitor tin cậy thu thập: ngày certificate, metadata fetch/validUntil/cacheDuration, khả năng dùng keytab và KVNO.

### 14.1. `FederationAssetMonitorDemo.java`

~~~java
import java.time.Duration;
import java.time.Instant;

public final class FederationAssetMonitorDemo {

    enum Status { OK, WARN, CRITICAL, UNKNOWN }

    record CertificateState(
        boolean loaded,
        boolean approvedTrust,
        Instant notBefore,
        Instant notAfter) {}

    record MetadataState(
        boolean signedAndTrusted,
        Instant effectiveValidUntil,
        Instant lastFetchedAt,
        Duration cacheDuration,
        boolean lastRefreshSuccessful) {}

    record KeytabState(
        boolean readable,
        boolean expectedPrincipal,
        boolean allowedEnctype,
        boolean canDecryptServiceTicket,
        int localKvno,
        int observedKdcKvno) {}

    static Status certificate(
            CertificateState c, Instant now) {
        if (!c.loaded()) return Status.UNKNOWN;
        if (!c.approvedTrust()) return Status.CRITICAL;
        if (now.isBefore(c.notBefore())
                || !now.isBefore(c.notAfter())) {
            return Status.CRITICAL;
        }
        if (!now.plus(Duration.ofDays(30))
                .isBefore(c.notAfter())) {
            return Status.WARN;
        }
        return Status.OK;
    }

    static Status metadata(
            MetadataState m, Instant now) {
        if (!m.signedAndTrusted()) {
            return Status.CRITICAL;
        }
        if (m.effectiveValidUntil() != null
                && !now.isBefore(m.effectiveValidUntil())) {
            return Status.CRITICAL;
        }
        if (m.lastFetchedAt() == null) {
            return Status.UNKNOWN;
        }
        if (!m.lastRefreshSuccessful()) {
            return Status.WARN;
        }
        if (m.cacheDuration() != null
                && !now.isBefore(m.lastFetchedAt()
                    .plus(m.cacheDuration()))) {
            // CACHE_STALE != METADATA_INVALID.
            return Status.WARN;
        }
        if (m.effectiveValidUntil() != null
                && !now.plus(Duration.ofDays(7))
                    .isBefore(m.effectiveValidUntil())) {
            return Status.WARN;
        }
        return Status.OK;
    }

    static Status keytab(KeytabState k) {
        if (!k.readable() || !k.expectedPrincipal()
                || !k.allowedEnctype()
                || !k.canDecryptServiceTicket()) {
            return Status.CRITICAL;
        }
        if (k.observedKdcKvno() < 0) {
            return Status.UNKNOWN;
        }
        if (k.localKvno() != k.observedKdcKvno()) {
            return Status.WARN; // canary passed during overlap
        }
        return Status.OK;
    }

    static void print(String name, Status status) {
        System.out.println(name + "=" + status);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T00:00:00Z");
        Instant started = Instant.parse("2026-01-01T00:00:00Z");

        print("certHealthy", certificate(
            new CertificateState(true, true, started,
                Instant.parse("2027-02-01T00:00:00Z")), now));

        print("certExpiring", certificate(
            new CertificateState(true, true, started,
                Instant.parse("2026-11-21T00:00:00Z")), now));

        print("certExpired", certificate(
            new CertificateState(true, true, started,
                Instant.parse("2026-11-06T00:00:00Z")), now));

        print("certUnknownTrust", certificate(
            new CertificateState(true, false, started,
                Instant.parse("2027-02-01T00:00:00Z")), now));

        print("metadataHealthy", metadata(
            new MetadataState(true,
                Instant.parse("2026-12-07T00:00:00Z"),
                now, Duration.ofDays(7), true), now));

        print("metadataStale", metadata(
            new MetadataState(true,
                Instant.parse("2026-11-30T00:00:00Z"),
                Instant.parse("2026-11-05T00:00:00Z"),
                Duration.ofDays(1), true), now));

        print("metadataExpired", metadata(
            new MetadataState(true,
                Instant.parse("2026-11-06T00:00:00Z"),
                now, Duration.ofDays(7), true), now));

        print("metadataUntrusted", metadata(
            new MetadataState(false,
                Instant.parse("2026-12-07T00:00:00Z"),
                now, Duration.ofDays(7), true), now));

        print("keytabHealthy", keytab(
            new KeytabState(true, true, true, true, 7, 7)));

        print("keytabRollover", keytab(
            new KeytabState(true, true, true, true, 6, 7)));

        print("keytabBroken", keytab(
            new KeytabState(true, true, true, false, 6, 7)));

        print("keytabKdcUnknown", keytab(
            new KeytabState(true, true, true, true, 7, -1)));
    }
}
~~~

### 14.2. Chạy

~~~bash
javac --release 17 FederationAssetMonitorDemo.java
java FederationAssetMonitorDemo
~~~

**Stdout chính xác:**

~~~text
certHealthy=OK
certExpiring=WARN
certExpired=CRITICAL
certUnknownTrust=CRITICAL
metadataHealthy=OK
metadataStale=WARN
metadataExpired=CRITICAL
metadataUntrusted=CRITICAL
keytabHealthy=OK
keytabRollover=WARN
keytabBroken=CRITICAL
keytabKdcUnknown=UNKNOWN
~~~

### 14.3. Phân tích

- `certExpired` là hard deadline đối với chính sách monitor X.509; **không khẳng định Spring SAML verification luôn tự reject** expired cert nếu explicit key trust.
- `metadataStale=WARN` vì quá cacheDuration nhưng `validUntil` vẫn còn; không gộp hai trạng thái.
- `metadataExpired=CRITICAL` vì effective validUntil đã qua.
- `metadataUntrusted=CRITICAL` ưu tiên vấn đề trust trước việc còn hạn.
- `keytabHealthy` và `keytabRollover` không có thuộc tính `notAfter`; dùng canary và KVNO. Mismatch nhưng decryption còn pass có thể là overlap cần theo dõi.
- `keytabBroken=CRITICAL` vì service ticket decryption không đạt.
- `keytabKdcUnknown=UNKNOWN` vì không đủ evidence KDC hiện tại dù local canary pass; không “đoán” OK.

Các boolean `signedAndTrusted`, `canDecryptServiceTicket` chỉ là **fixtures mô phỏng**. Production phải lấy từ XML signature validator và GSS/Kerberos canary thật, không đọc flag do browser/user tự gửi. `Duration.ofDays` ở demo chỉ áp policy cục bộ; XML Schema `cacheDuration` cần parser đầy đủ như mục 6.

## 15. Kiểm thử và báo cáo metadata expiration

### 15.1. Kịch bản validUntil so với cacheDuration

Giả sử metadata fetched lúc 00:00Z, `cacheDuration=PT6H`, `validUntil` còn 10 ngày:
- 05:00Z: chưa tới thời điểm cần refresh.
- 07:00Z: cache đã stale, job phải thử refresh/báo WARN nếu thất bại; metadata chưa tự invalid chỉ vì 6 giờ qua.
- Đến `validUntil`: metadata đã invalid theo chuẩn, không dùng.
- Nếu parent `EntitiesDescriptor` hết hạn sớm hơn child, dùng effective validUntil sớm hơn.
- Nếu XML metadata không có signature/trust contract, việc fetch mới không tự làm nó đáng tin.

### 15.2. Dữ liệu cần lưu khi refresh

~~~text
registration_id=corp
source_url_ref=approved-idp-metadata
http_result=200
xml_parse=PASS
metadata_signature=PASS
entity_id=EXPECTED
effective_valid_until=2026-12-31T00:00:00Z
cache_refresh_due_at=2026-11-07T06:00:00Z
signing_keys=old+new
candidate_digest=opaque-sha256
runtime_applied_digest=opaque-sha256
last_applied_at=2026-11-07T00:05:00Z
canary_signed_login=PASS
~~~

Đây là example log **không chứa private key/SSO tokens**. Khi metadata fetch fail, giữ good snapshot chỉ theo policy; nếu snapshot quá validUntil, không dùng. Giữ cảnh báo `last_refresh_success_at` bị stale và promote failure, đừng ẩn lỗi vì request hiện tại vẫn pass.

### 15.3. Rủi ro metadata replay/downgrade

Một kẻ tấn công có thể cố thay metadata endpoint bằng bản **signed nhưng cũ** chứa key đã bị revoke nếu hệ thống không kiểm validUntil/version/anti-rollback. Cần:
- signed metadata source trust;
- effective validity và anti-rollback/version rules theo profile;
- chặn tự chuyển từ new key về compromised old key ngoài approved overlap;
- audit key-set diff, issuer/endpoint change và signed metadata validation result;
- có ticket/approval cho đổi trust anchor;
- không tin key mới được công bố bởi tài liệu chưa verify chỉ vì metadata X.509 date còn hạn.

## 16. Rollover không gián đoạn: chứng thư SAML

### 16.1. IdP đổi signing key

~~~text
Phase 1:  Preannounce + owner confirms fingerprints
Phase 2:  IdP metadata publishes old and new verification certs
Phase 3:  SP fetches, validates, promotes both keys
Phase 4:  SP canary accepts both signed fixture versions
Phase 5:  IdP starts signing with new key
Phase 6:  Prod SAML login success monitored per replica
Phase 7:  Old key retired after overlap agreed with partners
~~~

Nếu IdP ký bằng new key **trước** khi SP trust metadata mới, nhiều users sẽ gặp login failures. Cần xác nhận từng node đã apply new key và kiểm thử trước switch.

### 16.2. SP đổi signing key

- SP tạo new private/public key pair qua Vault/PKI; bảo vệ private key.
- SP công bố new public certificate qua metadata; IdP import/verify.
- Trong overlap, IdP tin old+new SP signing certificates theo khả năng provider.
- SP chuyển AuthnRequest/LogoutRequest signing sang new key khi đối tác xác nhận.
- Monitoring kiểm tra actual signed AuthnRequest, không chỉ SP XML metadata.
- Old key retire theo thỏa thuận, không xóa trước khi rollback windows đóng.

### 16.3. SP đổi decryption key

- IdP phải encrypt sang new SP public key sau khi đã được công bố/approved.
- SP giữ old private key cho in-flight responses đến hạn, nếu policy cho phép.
- Test fixtures encrypted with old/new certs để chắc chắn decryption path hoạt động.
- Monitor failures theo encryption key fingerprint/registration, nhưng không log raw decrypted XML.

### 16.4. Thay certificate “sớm” không thay key tùy ý

Một IdP có thể phát cert mới cùng public key nhưng khác dates, hoặc key pair mới. Đừng dùng `subject CN`/`serial` duy nhất để suy thay key; so SHA-256 cert fingerprint và **public key identifier** theo policy. Một cert chỉ mới hơn `notAfter` không tự được trust nếu signer/source metadata không được duyệt.

## 17. Rollover keytab/Kerberos qua nhiều replicas

### 17.1. Các bước

1. Inventory service principal, KDC realm, current KVNO/enctypes, keytab version trên A/B/DR, canary success.
2. Chốt rotation plan với KDC/AD admin, key management policy, target enctypes và khả năng giữ old keys/tickets.
3. Tạo new service key/keytab trong workflow được ủy quyền; **đừng chạy `ktadd` một cách tùy tiện**.
4. Phân phối secrets qua Vault/service identity, verify owner/group/file mode, không log hash keytab công khai.
5. Cập nhật từng node theo kế hoạch để tránh split-brain; kiểm tra GSS acceptor sử dụng file mới sau restart/reload đúng thực tế.
6. Thử KDC ticket mới và old tickets còn hiệu lực ở môi trường cho phép; kiểm tra `kvno -k` cùng application SPNEGO canary.
7. Đảm bảo HTTP 401 Negotiate challenge/response thành công, phân quyền local không bị ảnh hưởng.
8. Quan sát GSS errors và credential cache/ticket lifetime trong overlap.
9. Khi KDC/IdP và toàn bộ replicas xác nhận ổn định, retire old keys/tickets theo policy.
10. Với DR region, cập nhật/canary keytab đúng thời điểm và owner acknowledgement.
11. Lưu secret rotation audit/rollback plan, nhưng **không** lưu keytab contents trong logs/tickets.
12. Nếu rollback cần KDC restore old KVNO, chỉ admin có quyền thực hiện, không tự copy old keytab rồi kỳ vọng KDC phát keys cũ.

### 17.2. Nguy cơ đặc thù

- KDC thay KVNO trước rollout, production node vẫn có old only → login failures.
- Node A đã restart với new key, Node B vẫn dùng old JAAS cached credentials → lỗi ngẫu nhiên theo load balancer.
- Principal được gắn sai `HTTP/host@REALM` do proxy hostname khác backend.
- Encryption types không tương thích Java runtime/KDC security policy.
- Clock skew quá lớn làm vé bị từ chối dù keytab đúng.
- Keytab permission quá rộng → nguy cơ lộ service long-term key; security incident, không chỉ rotation ticket.
- Keytab mtime thay do restore backup nhưng key version không đổi → false alarm.
- Canary chỉ chạy một node và báo overall green trong khi node còn lại lỗi.

## 18. Phân tầng cảnh báo để tránh tự gây outage

### 18.1. Phân biệt các trạng thái

| Trạng thái | Ví dụ | Ứng xử |
| --- | --- | --- |
| `OK` | Cert đủ hạn, metadata fresh/trusted, canary pass. | Theo dõi bình thường. |
| `WARN` | Cert còn 20 ngày, metadata cache stale, KVNO mismatch nhưng canary pass. | Ticket và theo dõi sát, không tự hạ service. |
| `CRITICAL` | Metadata validUntil expired; SAML signature untrusted; canary Kerberos decrypt fail. | Incident/fail closed trên luồng tin cậy, khôi phục. |
| `UNKNOWN` | Collector ngừng báo, không truy vấn KDC được, runtime state không xác định. | Alert monitoring gap, probe lại có kiểm soát. |
| `IN_MAINTENANCE` | Rotation window được duyệt, old+new overlap. | Không suppress hard auth failures/compromise; chỉ điều chỉnh alert noise. |
| `COMPROMISED` | Private key/keytab bị lộ. | Emergency revoke/rotate, incident response, forensic. |

**Không biến một cảnh báo “cert còn 30 ngày” thành Spring readiness DOWN** nếu SP vẫn hoạt động. Ngược lại, metadata invalid/untrusted không được “đánh xanh” chỉ vì có cache. Liveness probe nên phản ánh tiến trình sống; readiness có thể phụ thuộc khả năng cung cấp dịch vụ nhưng cần đo đúng ảnh hưởng, không kéo toàn cụm xuống do một dependency tạm hỏng.

### 18.2. Alert ownership

- IAM/IdP owner chịu trách nhiệm IdP signing cert và metadata publication.
- Platform/SP owner chịu trách nhiệm runtime registration, SP signing/decrypt keys, reload, consumer metadata và canary.
- Security/PKI owner chịu trách nhiệm trust anchors, PKIX policies và revoked/compromised keys.
- Kerberos/AD owner chịu trách nhiệm service principal, KDC keys/KVNO, enctypes.
- SRE owner chịu trách nhiệm alerting, deployment, node drift, dashboards và incident response.
- Business owner xác nhận SLA, maintenance window và quyền fallback được duyệt.

Mỗi alert phải có **runbook link, asset ID, severity, deadline, owner, last-success/last-apply và escalation timer**, không chỉ một email “cert expired”.

## 19. Bộ kiểm thử QA

| ID | Tình huống | Kết quả cần đạt |
| --- | --- | --- |
| O01 | IdP signing X.509 còn hơn 90 ngày. | OK; fingerprint/owner rõ. |
| O02 | IdP signing cert còn 30 ngày. | WARN/escalation theo threshold. |
| O03 | IdP cert đã qua notAfter. | Monitor CRITICAL, kiểm tra policy runtime explicit-key vs PKIX. |
| O04 | Cert có notBefore tương lai. | NOT_YET_VALID; không chỉ xem notAfter. |
| O05 | SP signing public cert đổi nhưng IdP chưa import. | Signed AuthnRequest canary fail, alert. |
| O06 | SP decryption key đổi, old ciphertext còn tới. | Giữ old key theo overlap; canary decrypt pass. |
| O07 | TLS leaf cert expired, SAML cert còn hạn. | TLS alert riêng, không gộp. |
| O08 | Intermediate CA expired/revoked, leaf còn hạn. | PKIX/TLS chain failure detected theo policy. |
| O09 | SAML explicit-key trust accept expired cert trong implementation. | QA ghi chính xác behavior, không mặc định PKIX. |
| O10 | CRL/OCSP unavailable. | Theo revocation policy; không tự tuyên bố checked. |
| O11 | IdP metadata có validUntil 5 ngày nữa. | Cảnh báo theo deadline. |
| O12 | IdP metadata validUntil đã qua. | INVALID, không dùng stale invalid instance. |
| O13 | Metadata cacheDuration đã qua nhưng validUntil còn. | STALE/WARN, thử refresh; không nhầm invalid. |
| O14 | Metadata EntitiesDescriptor cha expire trước child. | Effective expiry lấy deadline cha phù hợp. |
| O15 | Metadata không có validUntil. | Local max-age policy/alert khi yêu cầu. |
| O16 | Metadata không có cacheDuration. | Apply configured refresh cadence; không cache vĩnh viễn. |
| O17 | Metadata signed bởi untrusted key. | Reject, không promote. |
| O18 | Metadata XML có XXE/oversized entity. | Parser từ chối theo policy. |
| O19 | Metadata HTTP 200 nhưng XML không parse được. | Giữ trusted snapshot trong giới hạn; báo lỗi. |
| O20 | Metadata HTTP 304. | Refresh semantics đúng, không gia hạn trust vô hạn. |
| O21 | Metadata mới đổi EntityID/SSO endpoint bất ngờ. | Quarantine/review, không auto promote. |
| O22 | Metadata mới có old+new verification keys. | Validate/accept cả hai theo policy. |
| O23 | IdP bắt đầu ký bằng new key trước SP trust. | Detect failures; rollback/coordinated cutover. |
| O24 | SP runtime trên node B còn metadata cũ. | Runtime digest mismatch alert. |
| O25 | SP metadata public ACS URL sai sau proxy. | Detect wrong hostname/HTTPS/port. |
| O26 | Cert trên disk đã cập nhật, Spring registration vẫn cũ. | Detect runtime stale; controlled reload. |
| O27 | Metadata refresh job ngừng chạy 24h. | Monitoring gap/freshness alert. |
| O28 | Keytab mtime đã một năm nhưng service ticket decrypt pass. | Không kết luận keytab expired. |
| O29 | `klist -k -t` timestamp cũ. | Không diễn giải là expiry date. |
| O30 | Script vô tình dùng `klist -K`. | Security QA FAIL; không log secret keys. |
| O31 | Keytab có wrong HTTP principal/realm. | Detect principal mismatch/canary fail. |
| O32 | Keytab KVNO=6, KDC phát 7, canary fail. | CRITICAL, không tắt Kerberos validation. |
| O33 | KVNO mismatch nhưng overlap canary pass. | WARN, theo dõi window; không false down. |
| O34 | Keytab chỉ có enctype không được phép. | Alert/security review, không bật DES/RC4 tùy tiện. |
| O35 | Keytab world-readable. | Security incident/permissions fix. |
| O36 | Keytab file có mặt nhưng process không đọc được. | Canary fail/permission alert. |
| O37 | Chỉ node A được cấp key mới, node B cũ. | Per-node alert, triển khai đầy đủ. |
| O38 | KDC offline khiến `kvno -k` fail. | Phân loại network/KDC failure, không kết luận keytab hỏng. |
| O39 | Clock skew làm GSS reject ticket. | NTP/time alert riêng. |
| O40 | SPN trùng/host mismatch sau load balancer. | Diagnose SPN registration, không sửa cert SAML. |
| O41 | Admin chạy `ktadd` khiến KDC KVNO rotate bất ngờ. | Alert change/incident, kontrolliertes rollout. |
| O42 | Old keytab rollback sau KDC key reset. | Không tin rollback chỉ bằng copy file, phối hợp KDC. |
| O43 | Kerberos ticket valid nhưng local app role thiếu. | 403 authorization, không coi keytab lỗi. |
| O44 | Cert sắp hết hạn nhưng IdP key đã đổi hôm nay. | Key drift/canary alert dù deadline còn xa. |
| O45 | Signed SAML Assertion có wrong audience/recipient. | Reject, không liên quan cert expiry check một mình. |
| O46 | IdP Response signed bằng key đã bị revoke. | Trust policy rejects/alerts, no stale metadata. |
| O47 | Metadata fetch thành công nhưng canary SAML login fail. | Incident runtime/auth path, không đánh green theo HTTP. |
| O48 | Spring readiness DOWN khi cert còn 30 ngày. | Test phát hiện policy gây self-inflicted outage. |
| O49 | Spring /actuator/health lộ keytab path/private key. | QA FAIL, hạn chế details/secure endpoint. |
| O50 | Browser nhận 401 Negotiate challenge ban đầu. | Không tính lỗi cho tới khi handshake fail. |
| O51 | Certificate expiry alert bị suppress toàn bộ trong maintenance. | Hard failures/compromise vẫn phải alert. |
| O52 | IdP signing key bị compromise. | Emergency revoke, metadata update, session/security review. |
| O53 | SP decryption key lộ. | Emergency rotation, forensic, protect in-flight data. |
| O54 | Keytab/service account secret lộ. | KDC/AD coordinated rotation, ticket/incident response. |
| O55 | Expired metadata vẫn được giữ ở cache. | Reject invalid instance; alert, không dùng mãi. |
| O56 | New metadata có wrong EntityID nhưng validUntil xa. | Reject trust/identity mismatch. |
| O57 | Prometheus không còn sample collector. | UNKNOWN/no-data alert, không lấy last green vĩnh viễn. |
| O58 | DR site keytab/metadata chưa sync sau rotation. | DR readiness test fail; rollout/verification. |
| O59 | TLS reverse proxy cert mới nhưng backend trust cũ. | Phân biệt TLS/SAML trust và runbook tương ứng. |
| O60 | Nâng Spring Security/IdP/KDC version. | Regression trust, metadata refresh và keytab canary. |

**Trong table O41, ý là controlled rollout theo change management; không áp một kịch bản “tự thay khóa” bằng monitor.**

### 19.1. Lab A — chứng thư và metadata

1. Tạo public X.509 test certificates (thật, không dùng production keys), chọn `notAfter` gần và xa.
2. Chạy `X509ExpiryAudit` và xác nhận trạng thái.
3. Dựng SAML metadata test có `validUntil` và `cacheDuration` khác nhau, kiểm tra stale vs invalid.
4. Đặt parent EntitiesDescriptor có deadline sớm hơn, xác nhận effective deadline.
5. Thử HTTP fetch fail và valid metadata snapshot còn hạn; xác nhận retry/alert trong policy.
6. Thử metadata signed bằng trusted/untrusted key và rotated KeyDescriptor old+new.
7. Kiểm tra Spring `RelyingPartyRegistrationRepository` đã apply keys mới, không chỉ URL metadata có 200.

### 19.2. Lab B — keytab không lộ secret

1. Dùng test Kerberos realm/AD service account và service principal giả.
2. Xác nhận `klist -k -e` hiển thị expected realm/KVNO/enctypes; **không dùng -K**.
3. Có test TGT được phép, thử `kvno -k` và GSS acceptor canary.
4. Thử node B chưa cập nhật keytab để xem intermittent login failure.
5. Mô phỏng KVNO transition có overlap, đánh WARN khi canary pass.
6. Test wrong SPN, missing keytab, permission denied, KDC outage và clock skew.
7. Kiểm tra ứng dụng không log raw Negotiate tickets/keys.

### 19.3. Lab C — rollback và disaster recovery

1. Test signed SAML Responses dưới old/new IdP certs trong overlap.
2. Test SP encrypted Assertions decrypt bằng old/new private keys.
3. Kiểm tra staging → prod → DR version manifest và owner signoff.
4. Thử deployment rollback nhưng metadata issuer đã quay key, bảo đảm rollback không phá trust.
5. Thu hồi một key trong trust list và xác nhận signed fixture với key đó không được tiếp tục chấp nhận ngoài policy.
6. Test incident khi secret compromise, không chỉ expiration tự nhiên.

## 20. Runbook theo từng loại sự cố

### 20.1. IdP signing certificate sắp hết hạn

1. Xác định asset, IdP entityID/registration, SHA-256 fingerprint, `notAfter` và tất cả consumers.
2. Liên hệ IdP owner lấy lịch rotation, cert mới và signed metadata/trust announcement.
3. Validate source/trust và expected issuer; đừng tải cert từ attachment chưa được xác minh.
4. Stage old+new verification keys, test signed fixtures ở staging.
5. Deploy/cập nhật RelyingPartyRegistration ở từng node, verify runtime version.
6. Chờ IdP chuyển ký bằng new key, monitor login success và signature errors.
7. Kết thúc overlap, retire old key theo change ticket.
8. Nếu đã hết hạn và policy quy định cấm, **không bypass** validation; khôi phục bằng approved trust material và rollback có điều kiện.

### 20.2. Metadata invalid hoặc stale

1. Đối chiếu `validUntil`/`cacheDuration` và thời điểm fetch UTC; xét parent hierarchy.
2. Nếu stale nhưng còn valid: retry fetch với backoff/jitter, alert theo max-stale policy.
3. Nếu invalid/expired: không promote hoặc tiếp tục dùng metadata instance đã invalid; lấy bản mới trusted.
4. Kiểm tra TLS, DNS, HTTP, XML parse, signature, issuer, endpoints, KeyDescriptors.
5. Kiểm tra Spring repository/cache đang dùng phiên bản nào và có reload thành công không.
6. Canaries: AuthnRequest → IdP → signed SAMLResponse → ACS và SP SLO khi dùng.
7. Phân loại partner outage/metadata endpoint error vs cấu hình local fail.
8. Không tắt metadata signature checks hoặc cho client chỉ định metadataUrl từ query.

### 20.3. Kerberos SPNEGO lỗi do keytab/KVNO

1. Xác định node, principal/realm, SPN mà browser đang yêu cầu, timestamp UTC của lỗi.
2. Phân biệt 401 challenge ban đầu với handshake/decrypt failure; thu reason class từ GSS/JAAS redacted log.
3. Dùng `klist -k -e` xem entries, không in key; so KDC KVNO/enctype qua authorized view.
4. Kiểm tra NTP, DNS, KDC, SPN duplicate, file permissions, correct service account.
5. Dùng test principal/TGT được phê duyệt, chạy `kvno -k` và actual SPNEGO canary.
6. Nếu key mismatch, phối hợp Kerberos admin rollout new keytab theo change plan; tránh `ktadd` ngẫu nhiên.
7. Verify mọi replicas + DR, login success, local account/tenant permissions.
8. Nếu keytab bị lộ, chuyển incident response và rotate/revoke theo KDC process.
9. Không đổi sang NTLM/Basic hoặc “accept any Negotiate token” để cứu lỗi.
10. Lưu incident summary với key versions/owner/status, không chứa secret.

### 20.4. Hai vấn đề xảy ra cùng lúc

Cert expiry, metadata refresh fail và keytab canary fail có thể đến từ nhiều hệ thống. Phân loại trước:
- SAML ACS signature reject hay browser TLS handshake fail?
- SPNEGO GSS ticket decrypt fail hay SAML signing error?
- Metadata source mới nhưng runtime chưa reload?
- Node-specific config drift hay toàn IdP/KDC outage?
- Local account disabled/403 dù authentication valid?

Một alert tổng `sso_login_failed` không đủ; cần tách `reason_class` để không thay nhầm cert hoặc keytab. Không dùng “tắt tất cả checks” như một phương án rollback.

## 21. Các lỗi thường gặp

| Nhận định sai | Vì sao sai? | Thay bằng |
| --- | --- | --- |
| “Keytab có ngày hết hạn giống cert.” | Keytab entry không có X.509 notAfter. | Rotation due + KVNO/enctype/decrypt canary. |
| “`klist -k -t` cho ngày keytab hết hạn.” | `-t` hiển thị entry timestamp. | Dùng admin policy/rotation record và canary. |
| “Chạy `klist -K` để debug là vô hại.” | `-K` lộ giá trị secret keys. | `klist -k -e`, không log key material. |
| “Metadata cacheDuration hết nên hết validity.” | Stale cache không luôn invalid. | Tách `refresh_due_at` và `validUntil`. |
| “Metadata validUntil hết vẫn dùng cache cũ vô hạn.” | Metadata instance invalid theo OASIS. | Fetch signed trusted new metadata/fail closed. |
| “HTTP 200 metadata = trust OK.” | XML có thể wrong issuer/key/signature. | Validate source/signature/EntityID/version. |
| “Đổi PEM trên disk là Spring nạp ngay.” | Registration có thể snapshot trong memory. | Reload/promotion check + canary. |
| “Cert còn hạn nên chữ ký đúng.” | Trust key/issuer/audience/algorithm có thể sai. | Protocol validation + approved trust. |
| “Cert expired nên mọi SAML SP mặc định reject.” | Explicit-key trust khác PKIX validity. | Version-specific behavior tests + policy. |
| “OCSP/CRL luôn được Spring tự gọi.” | Tùy implementation/trust model. | Định nghĩa revocation policy, test thực. |
| “Dùng cùng TLS cert cho SAML signing.” | Hai mục đích và trust boundaries khác. | Separate inventory/keys/permissions. |
| “KVNO mismatch là chắc chắn outage.” | Overlap/retained keys có thể vẫn accept. | Correlate canary, KDC policy, node state. |
| “Chạy lại kadmin ktadd chỉ để lấy file.” | Có thể randomize keys/change KVNO. | Controlled KDC/AD key rotation process. |
| “Keytab nằm trong Git/image nhưng mã hóa là được.” | Long-term service secret vẫn lộ theo distribution. | Vault/secret mounts/permissions. |
| “SP public metadata có cert mới nghĩa IdP đã nhận.” | Partner cần import/refresh. | Partner signoff + signed request canary. |
| “Actuator warning nên kill toàn bộ pods.” | Self-induced outage. | Alert pre-expiry, readiness theo thực tế. |
| “KDC outage thì bỏ ticket validation.” | Mở lỗ hổng impersonation. | Approved fallback + fail closed policy. |
| “Một node canary pass thì toàn cluster tốt.” | Keytab/metadata drift giữa replicas. | Per-node/region canaries and digest. |
| “Hết hạn X509 là cùng lúc hết hiệu lực SAML metadata.” | Hai field độc lập. | Monitor cả cert dates và metadata validity. |

## 22. Checklist production

- [ ] Inventory đầy đủ IdP verify, SP signing, SP decryption, TLS leaf/chain, metadata, Kerberos keytab.
- [ ] Mỗi asset có owner, environment, entityID/registrationId, trust source, fingerprint/digest, timeline và runbook.
- [ ] Monitor X.509 `notBefore/notAfter` cho **mọi certificate đang dùng**, không chỉ file đầu tiên.
- [ ] Rõ policy SAML explicit-key trust so với PKIX/CRL/OCSP, không suy default.
- [ ] Metadata `validUntil`, `cacheDuration`, parent precedence và local max-age được xử lý đúng.
- [ ] Metadata signature/trust source, XML parsing security, EntityID/endpoint diff được kiểm tra.
- [ ] Alert phân biệt CACHE_STALE, METADATA_INVALID, UNTRUSTED, RUNTIME_STALE.
- [ ] Monitor metadata source fetch success và Spring runtime `RelyingPartyRegistration` applied version.
- [ ] Spring registration reload được test theo framework/version; không giả định file đổi được load tự động.
- [ ] Signed SAML login/AuthnRequest/ACS/logout canaries có test fixtures và trust keys được phê duyệt.
- [ ] IdP signing rollover có old+new verification overlap và partner signoff.
- [ ] SP signing rollover có IdP confirmation, test actual signed requests.
- [ ] SP decryption rollover không xóa private key cũ trước khi hết in-flight window.
- [ ] TLS endpoint live cert/chain được giám sát độc lập với SAML cert.
- [ ] Keytab principal/realm/SPN, KVNO, enctype, ACL và runtime secret version được kiểm tra per-node.
- [ ] **Không** có metric “keytab notAfter”; dùng rotation due/KDC policy/canary.
- [ ] `klist -K` không được dùng trong monitor/CI/logs; keytab không được commit hay đính kèm tickets.
- [ ] `kvno -k`/GSS acceptor canary chạy bằng test principal/credential được phép.
- [ ] Không tự chạy destructive `kadmin ktadd`/password reset trong monitor job.
- [ ] Monitor alert khi KDC KVNO thay và nodes chưa rollout, nhưng xét overlap/canary.
- [ ] NTP/clock skew, DNS, KDC outage và SPN mismatch có diagnostics riêng.
- [ ] Có thresholds/owner escalation 90/60/30/14/7/1 ngày theo tier, không silent expiry.
- [ ] Có stale collector/`UNKNOWN` alert, không lấy last-known OK mãi.
- [ ] Health/Actuator không tiết lộ secret; liveness không phụ thuộc IdP latency trực tiếp.
- [ ] Đã test readiness policy tránh tự loại toàn cluster khi cert chỉ sắp hết hạn.
- [ ] DR/secondary regions có metadata/cert/keytab/secret sync và canaries.
- [ ] Change/incident plans gồm rollback constraints, per-node readback và partner communication.
- [ ] Fail closed khi metadata invalid/untrusted; không disable signature/SPNEGO verification để cứu outage.
- [ ] Test O01–O60 hoặc coverage tương đương trong staging và khi nâng phiên bản.

## Ghi nhớ

> **Chứng thư X.509 có ngày hiệu lực, metadata SAML có giới hạn hiệu lực và làm mới, còn keytab chứa Kerberos service keys không có ngày hết hạn kiểu X.509.** Để vận hành an toàn, giám sát **cả deadline lẫn trust/actual runtime state**: certificate fingerprints, metadata validUntil/cacheDuration và refresh/applied digest, keytab principal/KVNO/enctype cùng ticket-decrypt canary. Luôn rollover có kế hoạch và kiểm thử end-to-end; không cho “metadata tải được” hoặc “file keytab còn tồn tại” thay thế bằng chứng SSO thật đang an toàn.

### Tài liệu chính thức và tham khảo

- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, signing/decryption/verification credentials và metadata handling.
- [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): parse IdP metadata và publish SP metadata.
- [Spring Boot — SAML2 Relying Party](https://docs.spring.io/spring-boot/reference/security/saml2.html): properties và cấu hình IdP/SP credentials.
- [Spring Boot Actuator — Endpoints/Health Indicators](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): HealthIndicator, readiness/liveness và kiểm soát endpoint details.
- [OASIS SAML V2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `EntityDescriptor`, `EntitiesDescriptor`, `KeyDescriptor`, `validUntil`, `cacheDuration`.
- [OASIS SAML V2.0 Errata 05, E94](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html): phân biệt metadata cache staleness và metadata validity.
- [OASIS Metadata Interoperability Profile](https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop-cd-01.html): metadata trust, signed metadata, expiry và rollover.
- [RFC 5280 — Internet X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): notBefore/notAfter, PKIX path validation và revocation.
- [MIT Kerberos — klist](https://web.mit.edu/Kerberos/krb5-current/doc/user/user_commands/klist.html): `-k` list keytab, `-e` enctypes, `-t` timestamps, `-K` prints secret key values.
- [MIT Kerberos — kvno](https://web.mit.edu/Kerberos/krb5-current/doc/user/user_commands/kvno.html): service ticket KVNO và `-k` keytab decryption test.
- [MIT Kerberos — kadmin](https://web.mit.edu/KERBEROS/krb5-1.21/doc/admin/admin_commands/kadmin_local.html): `ktadd` và ảnh hưởng tới principal keys/rotation.
- [Spring Security Kerberos Extension](https://github.com/spring-projects/spring-security-kerberos): SPNEGO provider/filter và keytab integration, kiểm tra Jakarta compatibility theo version.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication failure handling và defense-in-depth.
