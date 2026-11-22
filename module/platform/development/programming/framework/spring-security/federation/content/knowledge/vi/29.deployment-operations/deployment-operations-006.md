# Quy trình trao đổi metadata và luân chuyển khóa có giai đoạn chồng lấp trong Spring Security federation

## 1. Vì sao không nên thay khóa SSO trong một lần deploy?

Trong hệ thống **Spring Security – federation** sử dụng **SAML 2.0**, Service Provider (**SP**, ứng dụng Spring Security/Relying Party) và Identity Provider (**IdP**, Asserting Party) trao đổi metadata để hiểu **entity ID, endpoint, binding, khóa công khai, thuật toán và điều kiện tin cậy** của nhau. Mỗi phía có **private key riêng**, không được chuyển private key cho phía đối tác.

Khi khóa ký của IdP hoặc khóa mã hóa của SP sắp hết vòng đời, thay khóa “một phát” thường gây outage:

~~~text
Ngày T0:
  IdP ký SAMLResponse bằng K_IDP_OLD.
  SP chỉ tin public key K_IDP_OLD.
  Người dùng login thành công.

Ngày T1 - ĐỔI KHÓA ĐỘT NGỘT:
  IdP chuyển sang ký bằng K_IDP_NEW.
  SP chưa tải metadata/cert mới, chỉ tin K_IDP_OLD.
  -> XML signature verification FAIL.
  -> Ứng dụng từ chối tất cả login dùng K_IDP_NEW.

Hoặc:
  IdP chuyển sang mã hóa Assertion cho K_SP_NEW.
  SP chưa lắp private key K_SP_NEW.
  -> EncryptedAssertion không giải mã được.
~~~

Cách vận hành có thể tránh gián đoạn là **luân chuyển khóa với giai đoạn chồng lấp (key rollover with overlap)**: **công bố trước khóa mới**, bảo đảm đối tác chấp nhận nó, **chỉ sau đó mới chuyển khóa đang sử dụng**, rồi tiếp tục **giữ khóa cũ đủ lâu** để các bản metadata cache và thông điệp còn đang trên đường truyền hết hiệu lực. Cuối cùng mới loại bỏ khóa cũ theo change plan.

Bài học thuộc nhóm **Triển khai và vận hành**, tập trung vào quy trình từ thiết kế, trao đổi metadata, vận hành key ring, rollout, kiểm thử, giám sát đến rollback. Sau khi học, bạn có thể:

1. Phân biệt khóa **IdP ký SAMLResponse** với khóa **SP ký AuthnRequest**, khóa **SP dùng giải mã EncryptedAssertion** và **trust anchor ký metadata**.
2. Kiểm đúng `<md:KeyDescriptor use="signing">`, `use="encryption"` và certificate chứa public key trong XML metadata.
3. Lập bảng **ai sở hữu private key, ai phải cập nhật public key** cho mỗi loại rotation.
4. Xây lịch **prepare → publish → propagate → activate → observe → retire**, tính cửa sổ overlap theo cache/fetch/độ trễ/rollback.
5. Trao đổi metadata qua **kênh được xác thực**, không chấp nhận certificate mới chỉ vì nó nằm trong một tài liệu chưa được tin cậy.
6. Hiểu giới hạn của Spring Security **`RelyingPartyRegistration`**, **`Saml2X509Credential`**, **`OpenSaml5AssertingPartyMetadataRepository`**, metadata endpoint và cache/refresh.
7. Thiết lập giai đoạn SP hỗ trợ **hai khóa giải mã** và hai khóa xác minh IdP, đồng thời chọn rõ khóa **signing đang hoạt động**.
8. Giữ các điều kiện **signature, issuer, audience, recipient, destination, InResponseTo, replay** xuyên suốt rotation; không tắt validation để “chữa” lỗi certificate.
9. Xây runbook phối hợp với IdP, multi-tenant, CI/CD, Kubernetes, HSM/KMS, quan sát và rollback.
10. Chạy demo **Java 17 độc lập** mô phỏng public key trust ring và encryption key overlap bằng **JCA RSA-SHA256, RSA-OAEP và AES-GCM**; phân biệt nó với SAML XMLDSig/XML Encryption thật.

**Thông điệp chính:** *Public key mới phải được công bố và được bên nhận tin cậy **trước khi** private key mới bắt đầu được sử dụng cho thông điệp live. Public key cũ không được bị loại bỏ cho tới khi mọi thông điệp có thể dùng key cũ đã hết vòng đời và đối tác đã đổi xong — ngoại lệ là sự cố lộ khóa cần phản ứng khẩn cấp.*

## 2. Phạm vi: metadata SAML khác JWKS OIDC và CAS

**Metadata SAML 2.0** thường là XML `<md:EntityDescriptor>` hoặc `<md:EntitiesDescriptor>` chứa các role:

- `<md:IDPSSODescriptor>`: IdP SSO/SLO endpoints và signing/encryption key descriptors của IdP.
- `<md:SPSSODescriptor>`: SP ACS/SLO endpoints, có thể có signing/encryption key descriptors của SP.
- `entityID`: định danh ổn định của từng SAML entity.
- `<md:KeyDescriptor>` và `<ds:KeyInfo>`: public key / X.509 certificate mà phía còn lại có thể dùng để xác minh chữ ký hoặc mã hóa.
- `validUntil` và `cacheDuration` (nếu có): thông tin validity/cache của metadata, không phải mặc định quyền tin tưởng mọi bản metadata không chữ ký.

**OIDC/OAuth 2.0** dùng discovery document và **JWKS** cho khóa ký JWT, `kid`, `jwks_uri`, token validation; ý tưởng **publish new key before switching signer, keep old until JWT expire** tương tự nhưng **không dùng SAML KeyDescriptor/XML metadata để diễn giải JWKS**. **CAS Service Ticket** là credential một lần, không phải signed JWT/JWKS key rollover; CAS có các cơ chế tin cậy/PKI riêng.

Vì vậy bài này **lấy SAML2 trong Spring Security làm tình huống chính**, cuối bài có bảng so sánh ngắn OIDC để tránh trộn giao thức.

## 3. Ai sở hữu khóa nào và ai phải làm gì?

| Mục đích | Bên sở hữu private key | Bên nhận public key | Hướng thông điệp | Khi rotate |
| --- | --- | --- | --- | --- |
| **IdP ký SAMLResponse/Assertion** | **IdP** | **SP** lưu certificate để verify | IdP → SP | SP phải tin new IdP signing public key **trước** IdP ký bằng private key mới |
| **SP ký AuthnRequest/LogoutRequest** | **SP** | **IdP** lưu public signing key của SP | SP → IdP | IdP phải tin new SP signing public key **trước** SP đổi signer |
| **SP giải mã EncryptedAssertion** | **SP** | **IdP** dùng SP encryption public key để mã hóa | IdP → SP | SP phải **cài private decrypt key mới trước** khi IdP mã hóa theo public key mới; giữ private old |
| **IdP giải mã thông điệp gửi từ SP** | **IdP** | SP dùng IdP encryption public key | SP → IdP | IdP phải cài private key mới trước khi SP chuyển encrypt |
| **Ký SAML metadata** | Metadata publisher/federation operator | Metadata consumer có **trust anchor độc lập** | Trao đổi metadata | Rotate **metadata signing trust** theo chu trình riêng; không nhầm với assertion signing |
| **TLS HTTPS metadata endpoint** | Server/proxy của endpoint | HTTP/TLS client trust store | Fetch metadata | TLS certificate rotation theo PKIX/CA/server name; không tự là SAML signing cert |

**Private key không có trong metadata SAML.** Phía nhận metadata chỉ cần **public key/certificate** cho verify hoặc encrypt. Nếu một “metadata export” chứa private key hoặc mật khẩu keystore, đó là sự cố bảo mật, phải dừng xuất bản.

### 3.1. Hai dòng thời gian ngược nhau

**Khi rotate khóa ký:**

~~~text
1. Producer tạo new private/public signing key.
2. Producer công bố new PUBLIC verification key bên cạnh old PUBLIC key.
3. Consumers refresh + tin được CẢ HAI.
4. Producer bắt đầu KÝ bằng new PRIVATE key.
5. Consumers vẫn verify old/new trong overlap.
6. Chờ in-flight/metadata cache/rollback hoàn tất.
7. Consumers thôi tin old PUBLIC key; producer bảo vệ/xóa old PRIVATE key theo policy.
~~~

**Khi rotate khóa giải mã ở SP:**

~~~text
1. SP tạo new decrypt private/public key.
2. SP cài new PRIVATE decryption key, vẫn giữ old PRIVATE key.
3. SP công bố cả old/new PUBLIC encryption keys trong metadata.
4. IdP refresh và kiểm rằng có thể chọn new public key.
5. IdP chuyển sang MÃ HÓA bằng new public key theo kế hoạch.
6. SP giải mã được bằng new hoặc old private key trong overlap.
7. Chờ message cũ/queue/replay windows hết hiệu lực.
8. SP ngừng giải mã bằng old private key và bỏ old public key khỏi metadata.
~~~

**Lưu ý:** chỉ “đưa cả hai encryption certificates vào metadata” **không bảo đảm IdP sẽ tự chọn đúng khóa mới** hoặc chọn theo thứ tự bạn mong muốn. SAML metadata có thể chứa nhiều keys, nhưng **sender-specific selection behavior** cần được xác nhận bằng test và thỏa thuận vận hành.

## 4. Đọc Metadata XML: entity, role, KeyDescriptor

Một metadata IdP có thể chứa **hai khóa ký được chấp nhận đồng thời**:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="signing">
    <!-- ds:KeyInfo / ds:X509Data / ds:X509Certificate
         chứa IdP PUBLIC CERTIFICATE old -->
  </md:KeyDescriptor>
  <md:KeyDescriptor use="signing">
    <!-- ds:KeyInfo / ds:X509Data / ds:X509Certificate
         chứa IdP PUBLIC CERTIFICATE new -->
  </md:KeyDescriptor>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.test/sso"/>
</md:IDPSSODescriptor>
~~~

**Đây là sơ đồ cấu trúc XML, không phải metadata hợp lệ để nhập vào IdP/SP.** Các comments chỉ chỉ nơi có ds:KeyInfo; metadata thật phải có đầy đủ namespace, `EntityDescriptor`, nội dung X.509 certificate Base64, thuộc tính và chữ ký metadata theo profile.

Với SP encryption:

~~~xml
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="encryption">
    <!-- SP PUBLIC encryption CERTIFICATE old -->
  </md:KeyDescriptor>
  <md:KeyDescriptor use="encryption">
    <!-- SP PUBLIC encryption CERTIFICATE new -->
  </md:KeyDescriptor>
  <md:AssertionConsumerService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://portal.example.test/login/saml2/sso/corp"
      index="0" isDefault="true"/>
</md:SPSSODescriptor>
~~~

### 4.1. Phân biệt `use` attribute

- `use="signing"`: key dùng để verify signatures/transport authentication theo SAML metadata semantics.
- `use="encryption"`: key thích hợp cho encrypt/wrap content encryption keys gửi tới entity.
- Khi **`use` bị bỏ trống**, profile metadata có thể diễn giải key áp dụng cho **cả signing và encryption**. Không giả định trường thiếu `use` luôn chỉ là signing.
- `ds:X509Certificate` chứa **certificate/public key**, không có private key.
- `md:KeyDescriptor` có thể có `EncryptionMethod` hoặc constraints liên quan thuật toán; bên gửi phải hỗ trợ matching algorithms.
- Metadata `entityID`, endpoints, bindings và requirements không được tự đổi cùng lúc với key rotation nếu không được quản lý như **một migration riêng**.
- Với multi-tenant, metadata IdP A không được tự được tin cho tenant B nếu không có explicit federation configuration.

### 4.2. Certificate SAML và certificate TLS

Chúng đều có thể ở dạng **X.509** nhưng vai trò khác nhau:

| Certificate | Quyền tin cậy | Nơi kiểm | Không được nhầm |
| --- | --- | --- | --- |
| SAML IdP signing cert | Public key được liên kết với IdP entity từ **trusted metadata/config** | XMLDSig validator | Không tự tin vì CN/CA TLS |
| SAML SP encryption cert | Public key dùng để mã hóa assertion cho SP | IdP encryption producer | Không phải certificate của browser HTTPS |
| Metadata signing cert | Trust anchor độc lập do federation/operator xác minh | Metadata signature verifier | Không dùng key mới trong metadata để tự xác minh cùng metadata |
| HTTPS server cert | PKIX/hostname/TLS trust | HTTP client/proxy | HTTPS hợp lệ không thay thế mọi metadata provenance controls |
| SAML SP signing cert | Public key IdP dùng để verify AuthnRequest | IdP SAML validator | Không cần đưa private signing key cho IdP |

Trong nhiều SAML profiles, certificate embedded trong metadata được dùng làm **public-key carrier/direct trust** chứ không nhất thiết phải có CA chain kiểu browser TLS. OASIS Metadata Interoperability Profile khuyến nghị consumer xác định trust từ **metadata đã được chấp nhận**; không tự áp một chính sách PKIX/OCSP riêng vào metadata keys như mặc định bắt buộc. Tuy nhiên tổ chức có thể có chính sách nội bộ về certificate validity, thuật toán, key sizes và HSM. **Không suy rằng một cert “chưa NotAfter” thì tự đáng tin, hoặc NotAfter của SAML cert được mọi implementation kiểm giống HTTPS.** Tối quan trọng là **trust provenance + crypto algorithm + key continuity**.

## 5. Trao đổi metadata an toàn: bootstrap trust trước rotation

Việc cập nhật metadata là **một thao tác thay đổi ranh giới tin cậy**. Attacker chỉ cần chèn public key của mình vào bản IdP metadata được SP chấp nhận là có thể làm SP tin các SAMLResponse mà attacker ký; do đó **refresh tự động nhưng không kiểm provenance có thể nguy hiểm hơn metadata tĩnh được phê duyệt**.

### 5.1. Metadata được tiếp nhận qua kênh nào?

Các cách hợp lý tùy môi trường:

1. **Signed metadata từ federation/IdP**, consumer có **metadata signature verification trust anchor được cấp qua kênh độc lập**. Xác minh signed root/chain/pin phù hợp, freshness, expiration và expected entityID.
2. **HTTPS endpoint đáng tin** cùng cơ chế xác thực upstream, certificate chain, hostname và provenance; tổ chức có thể bổ sung **fingerprint hoặc checksum được xác nhận out-of-band** trước lần bootstrap.
3. **Metadata file/artefact được chuyển qua change-managed repository**: có review, ký artefact/attestation, checksum, provenance, kiểm version và deploy theo rollout.
4. **Federation operator registry** đã có SLA, metadata signature, validity/cache controls và documented trust anchors.

Không phải cứ metadata URL có `https://` là đã có kiểm chữ ký **XML metadata**. Nó chỉ nói TLS transport có thể được xác minh; **trust ban đầu và tính toàn vẹn XML** vẫn phụ thuộc mô hình cung cấp.

### 5.2. Một sự thật về Spring Security hiện đại cần nhớ

Spring Security 7.x tài liệu mô tả `OpenSaml5AssertingPartyMetadataRepository`:

- Có thể dùng **OpenSAML MetadataResolver** để refresh metadata theo expiry/cache policy.
- Có thể xác minh chữ ký metadata bằng `verificationCredentials(...)`.
- **Nếu không cung cấp metadata verification credentials, component sẽ KHÔNG làm metadata signature validation**.
- `fromTrustedMetadataLocation(...)` biểu đạt một nguồn metadata đã được tổ chức quyết định tin; đây **không thay thế** việc phê duyệt provenance và không tự biến certificate assertion trong XML thành trust anchor của metadata.
- Phải phân biệt **trust anchor ký metadata** với **IdP keys để verify SAMLResponse**; hai vòng xoay khóa riêng biệt.

Ví dụ minh họa Spring Security 7.x:

~~~java
// Fragment tích hợp Spring Security 7/OpenSAML 5,
// không chạy độc lập nếu thiếu project/dependencies.
Saml2X509Credential metadataSigner =
    Saml2X509Credential.verification(
        metadataSigningCertificateApprovedOutOfBand);

AssertingPartyMetadataRepository metadataRepository =
    OpenSaml5AssertingPartyMetadataRepository
        .withMetadataLocation("https://idp.example.test/metadata")
        .verificationCredentials(credentials ->
            credentials.add(metadataSigner))
        .build();
~~~

`metadataSigningCertificateApprovedOutOfBand` là biến đã được nạp bởi hệ thống trust provisioning có kiểm soát; **không phải certificate lấy ngẫu nhiên từ metadata đang cần verify**. Đoạn này chỉ minh họa API; cần imports, bean wiring, repository refresh cache và policy xử lý failure theo version project.

### 5.3. Quy trình trao đổi trước ngày rotation

Một change request nên có:

- **Entity ID** IdP và SP, registrationId và tenant.
- **Public metadata endpoint** cố định hoặc signed file location.
- **SP ACS, SSO, SLO URLs** đúng public scheme/host/path.
- Loại khóa: **IdP assertion signing**, **SP AuthnRequest signing**, **SP decrypt**, hay **metadata signing trust**.
- **Current và new SHA-256 certificate fingerprint/public-key fingerprint**; đối chiếu qua kênh xác thực độc lập.
- Bên nào quản lý private key, HSM/KMS/key vault alias, nơi lưu và quyền truy cập; không trao đổi private key.
- Ngày **publish**, cửa sổ **propagation**, ngày **activate**, giai đoạn **overlap**, ngày **retire** và deadline rollback.
- Metadata `validUntil`/`cacheDuration` nếu áp dụng, cache TTL thực của đối tác, chính sách backoff khi fetch fail.
- Thời hạn SAMLResponse/Assertion/AuthnRequest, in-flight queues, clock skew, logout messages và các vùng địa lý/replicas.
- Ai phải **acknowledge**: IdP operator, SP operator, network/secret management, on-call, security approver.
- Runbook/rehearsal, canary cohort, monitoring, rollback owner và contact trong change window.

**Không dựa duy nhất vào “đã gửi email certificate mới”**; cần kiểm đối tác đã **nạp thật và dùng được** key mới trước cutover.

## 6. Quy trình 6 pha chuẩn cho key rollover có chồng lấp

<escape></escape>

| Pha | Trạng thái | Việc phải làm | Điều kiện chuyển pha |
| --- | --- | --- | --- |
| **P0 Inventory** | Chỉ K_old | Ghi metadata hiện tại, fingerprints, issuer/ACS/roles, consumers và cache behavior | Biết đầy đủ bên nào dùng key |
| **P1 Prepare** | K_old active, K_new offline | Sinh key pair mới, kiểm crypto, cài/giữ private key trong đúng security boundary | Test cert/key match và private key không rò |
| **P2 Publish** | Metadata chứa old + new | Ký/triển khai metadata, xác nhận signature/provenance, thông báo đối tác | Metadata mới được phân phối an toàn |
| **P3 Propagate/overlap** | Consumers tin cả old/new; old thường vẫn active | Refresh, kiểm fingerprint, canary cả hai key, ghi acknowledgment | Tất cả consumers critical sẵn sàng |
| **P4 Activate** | Producer chuyển sang key mới; consumers vẫn tin cả hai | Canary rollout, live signed/encrypted flows, monitor, rollback sẵn | New-key flow pass ổn định |
| **P5 Retire** | Chỉ new còn được tin/dùng | Sau TTL/in-flight/rollback window, bỏ old khỏi metadata/trust/decrypt ring; kiểm negative test | Không còn use hợp lệ của old key và security approval |

**Không tạo khoảng “chỉ K_new” ở consumer khi producer vẫn dùng K_old**. Giai đoạn P3/P4 phải thực sự tồn tại, không chỉ là hai certificates được lưu trên một máy mà service chưa nạp chúng.

### 6.1. Timeline dễ kiểm chứng

~~~text
Time ---------------------------------------------------------->

Producer metadata:
  [ OLD key only ] [ OLD + NEW published ........ ] [ NEW only ]

Producer active signer:
  [ OLD signs ................................ ] [ NEW signs .... ]

Consumer trusted verification set:
  [ OLD only ]  [ OLD + NEW verified ............ ] [ NEW only .... ]

                                  ^
                             CUTOVER chỉ sau khi
                        tất cả critical consumers cập nhật

Overlap:
  T_publish_new ... T_retire_old
  bao gồm propagation + retry/cache + response lifetime + rollback margin
~~~

**Thời gian chồng lấp không có một con số chuẩn chung**. Tùy số lượng đối tác, cách cache metadata, SLA, federation operator, nhu cầu rollback và chiều tin cậy.

### 6.2. Xác định cửa sổ overlap

Các biến cần xem:

- `P`: giới hạn **max metadata cache freshness / refresh interval** mà consumers thực sự sử dụng.
- `D`: độ trễ phân phối cấu hình, nhiều replicas/regions và thông báo đối tác.
- `M`: thời gian sống tối đa của message/artifact đang truyền, queue, browser redirects, logout messages.
- `S`: allowed clock skew và safety margin.
- `R`: cửa sổ quyết định rollback/do security review.

Một **upper-bound vận hành bảo thủ** có thể đặt:

~~~text
overlap_window >= P + D + M + S + R
~~~

Đó là **công thức lập kế hoạch**, không phải điều khoản bắt buộc của SAML standard. Nếu có bằng chứng independent từ từng partner rằng metadata đã cập nhật, có thể thay giả định cache bằng **acknowledgment/observed key acceptance** theo policy; tuy nhiên vẫn cần M/S/R thích hợp. Nếu một consumer không giới hạn cache TTL hoặc không thể nhận cả hai keys, **không thể mặc định áp công thức rồi cutover an toàn**; cần điều phối manual migration, dedicated window hoặc giải pháp hỗ trợ.

### 6.3. Lưu ý metadata `validUntil` và `cacheDuration`

- `validUntil` là giới hạn hiệu lực của metadata instance, nếu có.
- `cacheDuration` gợi ý caching metadata; việc consumer thực hiện thế nào phụ thuộc resolver/config/cache/network.
- HTTP `Cache-Control`, ETag, CDN proxy, Spring cache TTL, federation aggregator và sidecar cache có thể là **những lớp độc lập**.
- `cacheDuration` **không có nghĩa tất cả đối tác sẽ refresh đúng ngày**; cần verify thực tế.
- Khi refresh metadata thất bại, **không auto fail-open nhận metadata không được verify** hoặc dùng snapshot đã hết hạn vô thời hạn. Có thể giữ **last-known-good** trong một cửa sổ đã phê duyệt và cảnh báo; nếu hết cửa sổ phải fail closed theo chính sách.
- Không xóa old verification key khỏi SP chỉ vì producer mới cập nhật `validUntil`; cần đảm bảo không còn messages và rollback constraints.

## 7. Luân chuyển IdP signing key: trường hợp phổ biến nhất

### 7.1. Bước chuẩn

**Bước 1 — IdP tạo new signing key K_IDP_NEW.** Dùng khóa RSA/ECDSA phù hợp thuật toán mà các SP hỗ trợ, private key ở HSM/KMS/keystore có access controls. Không dùng lại key bị compromise nếu đó là sự cố cần rotate khẩn cấp.

**Bước 2 — IdP cập nhật metadata:** cùng `entityID`, role `IDPSSODescriptor`, thêm `<KeyDescriptor use="signing">` của new public certificate bên cạnh old. **Giữ active signer là OLD** trong giai đoạn đầu.

**Bước 3 — SP cập nhật trust:** tải metadata **được xác minh**, thấy cả OLD + NEW trong cùng IdP role. Nếu SP dùng static certificates, thay cấu hình verification credentials thành danh sách old/new và deploy lên **mọi instance**.

**Bước 4 — SP xác nhận:** test signed assertions từ cả old và new ở staging, kiểm issuer/audience/recipient/destination/time và quyền local. SP gửi **acknowledgment** về hash/fingerprint new key và trạng thái production.

**Bước 5 — IdP chuyển active signer NEW:** chỉ sau khi các SP critical sẵn sàng. Dùng canary/traffic gate nếu IdP hỗ trợ. Mọi SAMLResponse mới được ký bằng private key NEW.

**Bước 6 — Giữ overlap:** SP tiếp tục verify chữ ký old và new. Không thay đổi trust của metadata issuer, không bỏ response checks. Monitor signing key fingerprint của messages đã được accepted/rejected.

**Bước 7 — Retire OLD:** sau khi tất cả partners cập nhật, max in-flight+skew và rollback window đã hết, loại old signing public key khỏi trusted metadata/trust store; revoke/delete/archive old private key theo tổ chức. Test message chỉ ký bằng OLD bị reject sau thời điểm retire (trừ trường hợp break-glass policy yêu cầu tạm phục hồi).

### 7.2. Điều gì sẽ hỏng nếu đảo thứ tự?

| Hành vi | Lỗi dễ xảy ra |
| --- | --- |
| IdP ký bằng NEW trước khi SP tin NEW | `Signature validation failed` / untrusted credential |
| SP xóa OLD khi IdP còn ký OLD | Login fail cho nhóm còn key cũ |
| IdP metadata mới nhưng Spring consumer cache chưa refresh | Vẫn chỉ có OLD trong RelyingPartyRegistration |
| SP tin certificate NEW qua email giả không có provenance check | Key substitution, attacker có thể ký assertion được SP chấp nhận |
| IdP đổi `entityID` cùng ngày xoay key nhưng SP không cập nhật | Issuer mismatch ngay cả khi signature đúng |
| Thay `SigningAlgorithms` cùng lúc mà SP/IdP không hỗ trợ | AuthnRequest/response signature algorithm mismatch |
| SP dùng NEW certificate làm metadata trust anchor tự động | Metadata injection / circular trust |
| Chỉ test happy-path sau cutover | Missing old-key in-flight, replay/tenant failures chưa được phát hiện |

### 7.3. Mô hình SP tin hai keys

~~~text
IdP metadata:
  entityID = https://idp.example.test/saml
  signing public keys = [K_IDP_OLD, K_IDP_NEW]

SP verification key ring for registration "corp":
  allowedSigners = [K_IDP_OLD, K_IDP_NEW]
  expectedIssuer = https://idp.example.test/saml

Incoming SAMLResponse:
  verify XMLDSig using a credential associated with expected issuer
  if verify succeeds -> still validate audience/recipient/destination/
                        InResponseTo/time/replay/account mapping
  otherwise -> FAIL CLOSED
~~~

SAML certificate không nhất thiết được chọn bằng một `kid` như JWT JWKS; XMLDSig `KeyInfo` có thể giúp tìm candidate key, nhưng **không được tin một certificate tự khai trong untrusted response chỉ vì có KeyInfo**. Candidate public key phải nằm trong **trust set được cấu hình từ nguồn đáng tin cho đúng issuer**.

## 8. Luân chuyển SP signing key: chiều tin cậy đảo lại

SP ký `AuthnRequest` hoặc `LogoutRequest`; IdP dùng **SP signing public certificate** từ SP metadata/registration để verify.

Thứ tự:

1. SP tạo `K_SP_SIGN_NEW`, giữ `K_SP_SIGN_OLD` active.
2. SP **công bố public signing cert OLD + NEW** vào metadata của đúng SP entity.
3. IdP import và xác nhận đã tin NEW; nếu IdP chỉ cho **một** SP signing certificate, phải làm migration/maintenance plan riêng.
4. SP đổi **active signing credential** sang NEW. Trong runtime nhiều signing credentials, hãy xác định API **chọn signer nào**, không mặc định tất cả IdPs thử mọi signing keys cho outgoing messages.
5. IdP giữ verify OLD + NEW trong thời gian còn signed requests/logout messages cũ hoặc rollback.
6. Sau thời hạn an toàn, SP metadata và IdP trust chỉ còn NEW.

Đừng gửi cả OLD và NEW private keys cho IdP. IdP chỉ cần **public certificate**. Nếu IdP yêu cầu một certificate qua portal thay vì metadata URL, phải lưu **ngày được import, fingerprint và xác nhận effective configuration**, không chỉ upload form.

**Một trường hợp rollout nguy hiểm:** hai SP replicas cùng một entityID nhưng replica A ký OLD, replica B ký NEW. Điều này chỉ an toàn khi IdP **đang tin cả hai**. Nếu IdP mới trust NEW, traffic đến replica A sẽ thất bại. Tránh dùng rolling deployment mà không kiểm key overlap.

## 9. Luân chuyển SP decryption key: thứ tự khác signing

Với encrypted SAML, IdP có thể lấy public encryption cert của SP từ SP metadata rồi mã hóa `EncryptedAssertion`. Spring Security SP cần **matching private key** để giải mã.

### 9.1. Thứ tự an toàn

~~~text
P0: SP decrypt private: [OLD]; IdP encrypt public: [OLD]
    -> old-encrypted assertion works.

P1: SP tạo NEW private/public.
    SP cài private: [OLD, NEW].
    SP metadata publish public encryption keys: [OLD, NEW].
    IdP vẫn chọn OLD.
    -> cả old và new đều decrypt được ở SP.

P2: IdP xác nhận đã refresh metadata + hiểu chọn NEW.
    IdP bắt đầu encrypt bằng NEW.
    SP private vẫn [OLD, NEW].
    -> new-encrypted assertion works.
    -> old encrypted in-flight still works.

P3: Sau in-flight/rollback:
    IdP không dùng OLD nữa.
    SP bỏ public OLD khỏi metadata và private OLD khỏi runtime.
    -> only NEW works.
~~~

**Không đưa NEW public certificate lên metadata nếu SP chưa có private key tương ứng trên toàn bộ replicas**: IdP có thể chọn NEW ngay sau refresh và làm hỏng login tại replica chưa được cập nhật.

**Không xóa OLD private key đúng lúc IdP vừa chuyển sang NEW**: browser/queue có thể còn encrypted assertions dành cho OLD, và rollback có thể cần decrypt OLD. Trong khi giữ old, giới hạn quyền dùng và theo dõi truy cập private key.

### 9.2. Nếu IdP không hỗ trợ hai encryption keys

Không phải IdP nào cũng:

- Có thể import nhiều `KeyDescriptor use="encryption"`;
- Chọn encryption public key theo metadata mới;
- Hỗ trợ cách chọn candidate keys hoặc thuật toán của SP;
- Tự refresh metadata mà không restart.

Khi đối tác chỉ chọn một encryption key, **phải có runbook phối hợp thời gian**: SP cài cả old/new private trước, IdP cutover new ở một thời điểm, SP giữ old private để xử lý in-flight. Có thể cần thay metadata representation/priority theo hướng dẫn **của chính IdP vendor**. **Thứ tự xuất hiện các KeyDescriptor không phải lời cam kết chuẩn hóa rằng IdP chắc chắn chọn mục đầu tiên**.

### 9.3. Signature, encryption, metadata là ba chuyện khác nhau

- **SP decryption**: local private key dùng unwrap content encryption key và decrypt assertion.
- **IdP signing verification**: SP dùng trusted IdP public key để verify XMLDSig.
- **Metadata signature verification**: SP dùng independent trusted federation/metadata signing key để verify tài liệu metadata.

Một assertion **giải mã thành công** chưa đủ tạo Authentication: vẫn phải validate XML signature, issuer, audience, recipient, destination, subject/time conditions, InResponseTo và replay; dữ liệu sau decrypt vẫn là **untrusted until validated**.

Spring Security 7.x `OpenSaml5AuthenticationProvider` có response/assertion decrypters và dùng `decryptionX509Credentials` đã đăng ký. Tự custom decrypter sai thứ tự chữ ký và decrypt có thể làm mất tính đúng đắn XMLDSig; ưu tiên defaults hoặc test nghiêm ngặt trước khi thay.

## 10. Luân chuyển chính khóa ký metadata: một lớp trust riêng

Đôi khi chính **metadata signing certificate** của federation operator sắp thay. Đây **không** chỉ là “thêm IdP assertion signing cert mới”.

Nếu consumer đang tin metadata signer `M_OLD`:

1. Nhà vận hành metadata cung cấp **M_NEW public key/trust anchor qua một kênh độc lập đã được xác thực**.
2. Consumer cấu hình metadata verifier tin **M_OLD + M_NEW** trong giai đoạn chồng lấp, nhưng vẫn chỉ nhận metadata có chữ ký hợp lệ bởi **trusted anchors**.
3. Metadata publisher chuyển sang ký XML metadata bằng private `M_NEW`.
4. Các consumers refresh và xác nhận signed metadata được verify.
5. Giữ `M_OLD` cho tới khi metadata cache/in-flight/rollback hết hạn; retire nó theo policy.

**Không lấy certificate ký metadata mới từ một XML metadata chưa được verify**, rồi dùng chính certificate đó verify cùng XML. Điều đó là **circular/self-declared trust**. Phải bootstrap new metadata signing trust bằng independent root/anchor hoặc quy trình ký chuyển tiếp được thiết kế và security review.

Nếu metadata bị kiểm chữ ký thất bại:

- **Không “thử tắt signature validation”** để hệ thống login trở lại.
- Không tự thêm certificates trong metadata vào trusted signing set.
- Giữ **last-known-good** chỉ trong giới hạn freshness đã phê duyệt, đánh dấu degraded/alert; xử lý theo fail-closed policy khi hết hạn.
- Kiểm signature algorithm, namespace, canonicalization, signed element/Reference và entityID đúng; không sửa raw XML sau ký.
- Phân biệt lỗi metadata signature và lỗi SAMLResponse signature trong log/metrics.

## 11. Spring Security: cấu hình credentials hỗ trợ overlap

### 11.1. Các vùng cấu hình

Trong Spring Boot, nhóm cấu hình thường là:

~~~text
spring.security.saml2.relyingparty.registration.<registrationId>
  .entity-id
  .assertion-consumer-service-location
  .signing.credentials[]
  .decryption.credentials[]
  .assertingparty
      .metadata-uri
      .verification.credentials[]
      .entity-id / sso-url (khi manual)
~~~

Các đường property và tên API phụ thuộc **Spring Boot/Spring Security version**. Tài liệu Spring Boot 4.1 hiện hành cho thấy các nhóm `signing.credentials[]`, `decryption.credentials[]` và `assertingparty.verification.credentials[]`. Khi dùng `metadata-uri`, metadata có thể cung cấp verification keys; cách precedence/caching cần test với configuration thật.

### 11.2. YAML minh họa: SP decrypt cả OLD+NEW; verify IdP OLD+NEW

Đây là **ví dụ cho chế độ cấu hình public/private key file qua Spring Boot**, dùng filenames có tính mô tả, không chứa bí mật trong bài. Nó minh họa một deployment **manually provisioned** với IdP verification credentials; **không đồng thời khai metadata-uri trong ví dụ này** để tránh hiểu nhầm hai nguồn trust có cùng precedence.

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "https://portal.example.test/saml2/metadata/corp"
            assertion-consumer-service-location: "https://portal.example.test/login/saml2/sso/corp"
            signing:
              credentials:
                - private-key-location: "file:/run/saml-keys/sp-sign-active.key"
                  certificate-location: "file:/run/saml-keys/sp-sign-active.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/saml-keys/sp-dec-old.key"
                  certificate-location: "file:/run/saml-keys/sp-dec-old.crt"
                - private-key-location: "file:/run/saml-keys/sp-dec-new.key"
                  certificate-location: "file:/run/saml-keys/sp-dec-new.crt"
            assertingparty:
              entity-id: "https://idp.example.test/saml"
              verification:
                credentials:
                  - certificate-location: "file:/run/saml-trust/idp-sign-old.crt"
                  - certificate-location: "file:/run/saml-trust/idp-sign-new.crt"
              singlesignon:
                url: "https://idp.example.test/sso"
                sign-request: true
~~~

**Cảnh báo phiên bản:** một số Spring Boot versions thể hiện thuộc tính SSO dưới `singlesignon.url`, các bản khác có ký hiệu/cấu hình biến thể. Hãy validate startup **với đúng version đang deploy**, dùng Spring Boot configuration properties reference và integration tests. Đây là **config sketch**, không khẳng định mọi property được hỗ trợ trên mọi nhánh Boot hoặc IdP.

**Tại sao signing.credentials chỉ có active?** Với outbound AuthnRequest, SP phải chủ động quyết định **private signer** đang active. Cấp hai signing credentials vào list không bảo đảm SP “ký cả hai”; nhiều implementations chọn một credential theo thứ tự/chính sách. Giai đoạn overlap thực chất nằm ở **bên IdP tin cả old/new public keys**, còn SP ký một key active cho từng request.

### 11.3. Java DSL: explicit key rings theo registration

Ví dụ Spring Security API, các biến certificate/private key phải được nạp an toàn trước:

~~~java
// Integration fragment (cần imports, Spring Security dependencies,
// PEM/PKCS#8 loader và tests của project).
Saml2X509Credential spActiveSign =
    Saml2X509Credential.signing(spSigningPrivateKey, spSigningCertificate);

Saml2X509Credential spOldDecrypt =
    Saml2X509Credential.decryption(spOldDecryptPrivateKey, spOldDecryptCert);
Saml2X509Credential spNewDecrypt =
    Saml2X509Credential.decryption(spNewDecryptPrivateKey, spNewDecryptCert);

Saml2X509Credential idpOldVerify =
    Saml2X509Credential.verification(idpOldSigningCertificate);
Saml2X509Credential idpNewVerify =
    Saml2X509Credential.verification(idpNewSigningCertificate);

RelyingPartyRegistration corp =
    RelyingPartyRegistration.withRegistrationId("corp")
        .entityId("https://portal.example.test/saml2/metadata/corp")
        .assertionConsumerServiceLocation(
            "https://portal.example.test/login/saml2/sso/corp")
        .signingX509Credentials(credentials -> {
            credentials.add(spActiveSign);
        })
        .decryptionX509Credentials(credentials -> {
            credentials.add(spOldDecrypt);
            credentials.add(spNewDecrypt);
        })
        .assertingPartyMetadata(party -> party
            .entityId("https://idp.example.test/saml")
            .singleSignOnServiceLocation("https://idp.example.test/sso")
            .verificationX509Credentials(credentials -> {
                credentials.add(idpOldVerify);
                credentials.add(idpNewVerify);
            }))
        .build();
~~~

Nếu dùng builder khởi tạo từ **existing registration/metadata**, hãy kiểm danh sách credentials đã có trước khi thêm, tránh duplicate hoặc accidental stale signer. Code không có `@Bean`/imports/keystore loader vì đây là **fragment giải thích**, không phải chương trình Java độc lập. Để production còn phải có signature/ACS/issuer/profile/endpoint controls và metadata trust provenance.

### 11.4. Metadata endpoint của Spring SP

Một `SecurityFilterChain` có thể bật SP metadata:

~~~java
@Bean
SecurityFilterChain samlFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/health").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .saml2Metadata(Customizer.withDefaults());
    return http.build();
}
~~~

Tài liệu Spring Security hiện hành nêu các endpoint:

~~~text
/saml2/metadata
/saml2/metadata/{registrationId}
/saml2/service-provider-metadata/{registrationId}
~~~

Dùng SP metadata endpoint **thực sự được chạy từ cấu hình mới** để gửi đối tác, không gửi một XML thủ công khác với runtime. Với reverse proxy, bảo đảm `entityID`/ACS là **public HTTPS URL**, không thành `http://pod:8080`. Kiểm metadata export có **old/new public certs đúng `KeyDescriptor use`**; có trường hợp automatic metadata generation không biểu diễn key-role/algorithm như người vận hành kỳ vọng, cần test XML đầu ra và IdP import.

### 11.5. IdP metadata refresh với Spring Security 7.x

Tài liệu `OpenSaml5AssertingPartyMetadataRepository` cho phép refresh expiry-aware bằng OpenSAML metadata resolver. Với **metadata đã được organization tin qua HTTPS/provenance**:

~~~java
AssertingPartyMetadataRepository idpMetadata =
    OpenSaml5AssertingPartyMetadataRepository
        .fromTrustedMetadataLocation(
            "https://idp.example.test/metadata")
        .build();
~~~

Khi yêu cầu **XML metadata signature verification**, tạo repository có trust credential độc lập:

~~~java
AssertingPartyMetadataRepository idpMetadata =
    OpenSaml5AssertingPartyMetadataRepository
        .withMetadataLocation(
            "https://idp.example.test/metadata")
        .verificationCredentials(credentials ->
            credentials.add(metadataSignerCredential))
        .build();
~~~

Hai đoạn là **pattern tích hợp từ Spring Security 7.x reference**, cần kết nối repository với `RelyingPartyRegistrationRepository`/registration mapping/secret sourcing và đúng dependency version. Nếu tự viết custom `MetadataResolver`, refresh/freshness/expiration có thể không tự tồn tại như implementation mặc định; kiểm scheduler/cache và failure policy.

**Cực kỳ quan trọng:** `verificationCredentials` ở ví dụ này là **để verify chữ ký XML metadata**, không phải `assertingparty.verification.credentials` dùng để verify **SAMLResponse/Assertion** trong một `RelyingPartyRegistration`.

## 12. Vận hành khóa và certificate trên Kubernetes/VM/HSM

### 12.1. Sinh khóa và phân phối

Yêu cầu tối thiểu:

- Sinh **private key mới** bằng CSPRNG trong HSM/KMS hoặc môi trường được phê duyệt; đủ key size/algorithm/rotation policy.
- Giữ private key riêng cho **signing** và **decryption** nếu kiến trúc cho phép; tách quyền để giảm blast radius.
- Ghi lại **key identifier nội bộ**, owner, creation/activation/retire timestamps, certificate serial/fingerprint và lifecycle status.
- Public cert có thể được publish qua metadata; private key phải nằm trong **Kubernetes Secret volume được bảo vệ, vault, KMS/HSM hoặc OS keystore**.
- **Không commit private PEM**, không paste private key vào ticket/slack/email/CI logs/metrics.
- Dùng least privilege, file permissions, encrypted storage at rest, secret mount path được bảo vệ và audit access.
- Đảm bảo **private key thực khớp certificate public key**; nhiều lỗi “invalid signature” chỉ do mounted key/cert thuộc hai lần rotate khác nhau.
- Nếu dùng HSM/PKCS#11, kiểm Spring provider/decrypter có hỗ trợ key operations và behavior đúng; không giả định mọi API chỉ nhận extractable private key.
- Nếu certificate bị compromise, dùng **emergency revocation** khác quy trình overlap thông thường; giữ compromised key chỉ để duy trì availability là nguy hiểm.

### 12.2. Kubernetes rolling deployment

~~~text
Release A:
  idpTrust = [IDP_OLD]
  spDecrypt = [SP_OLD]

Release B (pre-stage):
  idpTrust = [IDP_OLD, IDP_NEW]
  spDecrypt = [SP_OLD, SP_NEW]
  spActiveSigner = SP_SIGN_OLD

IdP/partner acknowledgment:
  all critical instances support new keys

Release C (activate):
  spActiveSigner = SP_SIGN_NEW
  still idpTrust = [IDP_OLD, IDP_NEW]
  still spDecrypt = [SP_OLD, SP_NEW]

Release D (retire):
  idpTrust = [IDP_NEW]
  spDecrypt = [SP_NEW]
~~~

Nếu cùng một entityId nhưng các pods có **khác trust rings**, login phụ thuộc load balancer chọn pod nào. Một canary test pass trên pod mới **không chứng minh** pods cũ đã hỗ trợ new key.

Các biện pháp:

- Triển khai pre-stage **đến tất cả pods/regions** trước khi nhà phát ký dùng new key.
- Readiness probe nên gắn với key material accessible/metadata freshness, không chỉ HTTP 200.
- Secret volume mount/atomic update không đồng nghĩa Java `RelyingPartyRegistration` đang chạy tự **reload keys**. Nhiều components chỉ nạp key vào bean khi startup; cần rolling restart, explicitly reload repository hoặc dynamic resolver được test.
- Nếu sử dụng Spring Session/Redis để giữ AuthnRequest correlation, không làm mất session trong rollout; test SP-initiated SAML callbacks đi vào hai pods khác nhau.
- Không xóa old secret data khi old private decrypt còn cần cho messages chưa xử lý.
- Kiểm quyền truy cập key trên non-root containers, volumes, file rotation và filesystem permissions.
- Metadata endpoints phía SP có thể được cache bởi CDN/proxy; test metadata content/fingerprints qua **đường public thật**.
- Với multi-tenant, keyrings và private keys có scope cho **registration/issuer/tenant** riêng; không trộn IdP A cert vào trust B chỉ vì cùng hostname.

### 12.3. Rollback an toàn

Một rollback sau signer cutover cần:

1. Chứng minh **old private signer** vẫn an toàn, có thể kích hoạt lại theo approval.
2. Chứng minh peers còn tin **old public signing key** trong overlap.
3. Dừng/ngăn new signer activation nếu metadata chưa sẵn sàng; rollback signer khi điều kiện đúng.
4. Không rollback SP private decryption xuống chỉ OLD nếu IdP **đã gửi EncryptedAssertion dành cho NEW**. Khi cần rollback ứng dụng, **giữ cả OLD+NEW decrypt keys**.
5. Nếu old key đã bị xóa khỏi metadata/trust vì retirement, rollback có thể yêu cầu **một staged rotation mới**, không đơn giản đổi một environment variable.
6. Lưu rollback deadline/owners và điều kiện “abort the change” rõ ràng.

**Không thực hiện rollback bằng cách tắt signature validation, chấp nhận mọi SAMLResponse hoặc mở trust toàn bộ certificates.**

## 13. OpenSSL: xác minh public cert, fingerprint và key match

Các lệnh dưới đây cần dùng trên **môi trường có quyền được cấp**, với file test/staging hoặc secrets được quản lý. Chúng không tự tạo trust chain; mục tiêu là kiểm file vật lý khớp kế hoạch.

### 13.1. Inspect X.509 certificate

~~~bash
openssl x509 -in idp-sign-new.crt -noout -subject -issuer -serial -dates
openssl x509 -in idp-sign-new.crt -noout -fingerprint -sha256
openssl x509 -in sp-dec-new.crt -noout -fingerprint -sha256
~~~

Fingerprint SHA-256 là công cụ để **xác nhận đúng artefact đã được đối tác phê duyệt**, không tự chứng minh certificate đó thuộc IdP nếu bạn lấy fingerprint và file từ **cùng một kênh chưa được tin cậy**.

### 13.2. So public key của private key và certificate

~~~bash
# Public key DER lấy từ private key; tránh in private key.
openssl pkey -in sp-dec-new.key -pubout -outform DER \
  | openssl dgst -sha256

# Public key DER lấy từ certificate.
openssl x509 -in sp-dec-new.crt -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256
~~~

Hai SHA-256 digest của **SubjectPublicKeyInfo DER** phải khớp nếu private key và certificate là một cặp. Nếu key được giữ trong HSM không extractable, dùng **ký/xác minh challenge hoặc tool HSM vendor** phù hợp, không cố export private key để kiểm.

### 13.3. Cách xử lý pem/der/pkcs12

- `PEM` chỉ là text armoring/Base64 có `-----BEGIN ...-----`, có thể chứa certificate, PKCS#8 private key hoặc loại key khác.
- `DER` là binary ASN.1, thường dùng cho certificate/key.
- `PKCS#8` là format private key, có thể encrypted hoặc unencrypted; không đồng nghĩa keystore.
- `PKCS#12` là container có thể giữ private key/certificate chain, được Java `KeyStore.getInstance("PKCS12")` đọc.
- `JKS` là Java keystore khác; `PKCS#11` là interface cho token/HSM, không phải file tương đương PEM.
- `X.509 certificate` chứa public key và metadata certificate; **không chứa private key**.

Ví dụ inspect PKCS#12 **không in private key**:

~~~bash
keytool -list -v -storetype PKCS12 \
  -keystore sp-keys.p12
~~~

Không hard-code keystore password trong command line/CI logs; dùng secret input facility hoặc password file phù hợp tool và environment. Tránh `openssl pkcs12 -nodes` trên máy chung vì có thể xuất private key dạng plaintext.

### 13.4. Lưu ý cấu hình Spring

Spring Security `Saml2X509Credential.signing(...)` cần **private key + certificate**; `verification(...)` chỉ cần **certificate/public key**; `decryption(...)` cần **private key + certificate**. Không đưa public verification cert vào signing credential rồi mong SP ký được.

Khi copy PEM từ Vault/Kubernetes:

- Đúng PEM boundary/newline và encoding.
- Đúng PKCS#8 private key format mà loader chấp nhận.
- Đúng key/cert pairing; check SHA-256 SPKI fingerprint.
- Đúng secret mount path/permission.
- Có restart/reload thực tế.
- Correct role `SIGNING/DECRYPTION/VERIFICATION` và thứ tự key selection ở runtime.

## 14. Java 17 độc lập: ký và giải mã trong giai đoạn overlap

Chương trình này **biên dịch và chạy với JDK 17+** mà không cần Spring, CAS, IdP hay OpenSAML. Nó minh họa hai chiều rotation có bản chất khác nhau:

- **IdP signing:** producer dùng RSA private key để ký một chuỗi mô phỏng assertion; SP có keyring trusted public keys và từ chối signature/key/issuer/audience không phù hợp.
- **SP decryption:** sender dùng SP public key để mã hóa **AES content key** bằng RSA-OAEP rồi mã hóa nội dung bằng AES-GCM; SP giữ private keys OLD+NEW trong overlap.
- Trước publish, new signer chưa được tin. Sau publish/refresh, OLD+NEW cùng được chấp nhận. Khi old retired, only new accepted.
- Trước khi cài new SP private key, encrypted message cho NEW không giải mã được. Sau pre-stage, cả hai decrypt. Sau retire old, old ciphertext không còn được giải mã.
- Cửa sổ cutover chỉ được mở khi **tất cả critical peers** đã đạt metadata epoch cần thiết.

**Không nhầm với XMLDSig/XML Encryption:** mã sử dụng `SHA256withRSA` và một định dạng envelope tự tạo bằng `Cipher` cho **mục đích giáo dục**. SAML thật dùng chuẩn XML signature/encryption, key resolution, RSA-OAEP parameter compatibility, signed XML canonicalization, certificate trust, metadata signature verification, Recipient/Destination/Audience/InResponseTo/replay. Demo **không parse metadata**, **không xác minh certificate chain hay metadata XML signature** và không chứng minh bất kỳ SAMLResponse thật nào hợp lệ. Trong comment, `stageKeys` chỉ nhận một keyring **giả lập đã được test-admin duyệt out of band**, không nhận keys từ browser hoặc metadata chưa verify. Không dùng chương trình này để tự thay thế Spring Security provider.

Tệp **SamlMetadataRolloverDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class SamlMetadataRolloverDemo {
    static final String ISSUER = "https://idp.example.test/saml";
    static final String SP = "https://portal.example.test/saml2/metadata/corp";
    static final SecureRandom RANDOM = new SecureRandom();

    record SignedAssertion(String issuer, String audience, String subject,
                           String keyId, byte[] signature) {}
    record EncryptedAssertion(String recipientKeyId, byte[] wrappedKey,
                              byte[] iv, byte[] ciphertext) {}

    static KeyPair rsa() throws GeneralSecurityException {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048, RANDOM);
        return g.generateKeyPair();
    }

    static byte[] payload(String issuer, String audience, String subject) {
        return (issuer + "\u001f" + audience + "\u001f" + subject)
            .getBytes(StandardCharsets.UTF_8);
    }

    static SignedAssertion sign(String keyId, PrivateKey key,
            String issuer, String audience, String subject)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initSign(key, RANDOM);
        s.update(payload(issuer, audience, subject));
        return new SignedAssertion(issuer, audience, subject,
            keyId, s.sign());
    }

    static boolean verify(SignedAssertion assertion,
            Map<String, PublicKey> trustedIdpKeys) {
        if (assertion == null || !ISSUER.equals(assertion.issuer())
                || !SP.equals(assertion.audience())) return false;
        PublicKey key = trustedIdpKeys.get(assertion.keyId());
        if (key == null) return false;
        try {
            Signature s = Signature.getInstance("SHA256withRSA");
            s.initVerify(key);
            s.update(payload(assertion.issuer(),
                assertion.audience(), assertion.subject()));
            return s.verify(assertion.signature());
        } catch (GeneralSecurityException ex) {
            return false;
        }
    }

    static EncryptedAssertion encrypt(String keyId,
            PublicKey spEncryptionPublicKey, String text)
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, RANDOM);
        SecretKey secret = generator.generateKey();

        byte[] iv = new byte[12];
        RANDOM.nextBytes(iv);
        Cipher data = Cipher.getInstance("AES/GCM/NoPadding");
        data.init(Cipher.ENCRYPT_MODE, secret,
            new GCMParameterSpec(128, iv));
        data.updateAAD(keyId.getBytes(StandardCharsets.UTF_8));
        byte[] ciphertext = data.doFinal(
            text.getBytes(StandardCharsets.UTF_8));

        Cipher rsa = Cipher.getInstance(
            "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        rsa.init(Cipher.ENCRYPT_MODE, spEncryptionPublicKey);
        byte[] wrapped = rsa.doFinal(secret.getEncoded());
        return new EncryptedAssertion(keyId, wrapped, iv, ciphertext);
    }

    static String decrypt(EncryptedAssertion envelope,
            Map<String, PrivateKey> spPrivateKeys) {
        PrivateKey key = spPrivateKeys.get(envelope.recipientKeyId());
        if (key == null) return null;
        try {
            Cipher rsa = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
            rsa.init(Cipher.DECRYPT_MODE, key);
            byte[] rawAes = rsa.doFinal(envelope.wrappedKey());
            javax.crypto.spec.SecretKeySpec secret =
                new javax.crypto.spec.SecretKeySpec(rawAes, "AES");

            Cipher data = Cipher.getInstance("AES/GCM/NoPadding");
            data.init(Cipher.DECRYPT_MODE, secret,
                new GCMParameterSpec(128, envelope.iv()));
            data.updateAAD(envelope.recipientKeyId()
                .getBytes(StandardCharsets.UTF_8));
            return new String(data.doFinal(envelope.ciphertext()),
                StandardCharsets.UTF_8);
        } catch (GeneralSecurityException ex) {
            // Production must log a redacted reason, not plaintext/key data.
            return null;
        }
    }

    static void stageKeys(Map<String, PublicKey> trust,
            Map<String, PublicKey> independentlyVerifiedMetadata) {
        // Caller must verify the metadata transport/signature OUTSIDE here.
        // In this lab the input is a trusted test-admin approved map.
        trust.clear();
        trust.putAll(independentlyVerifiedMetadata);
    }

    static void check(String name, boolean ok) {
        System.out.println(name + "=" + ok);
        if (!ok) throw new AssertionError(name);
    }

    public static void main(String[] args) throws Exception {
        KeyPair idpOld = rsa(), idpNew = rsa(), attacker = rsa();
        KeyPair spOld = rsa(), spNew = rsa();

        Map<String, PublicKey> idpTrust = new HashMap<>();
        stageKeys(idpTrust, Map.of("idp-2025", idpOld.getPublic()));
        SignedAssertion oldMessage = sign("idp-2025",
            idpOld.getPrivate(), ISSUER, SP, "alice");
        SignedAssertion newMessage = sign("idp-2026",
            idpNew.getPrivate(), ISSUER, SP, "alice");

        check("oldSignatureAcceptedInitially",
            verify(oldMessage, idpTrust));
        check("newSignatureRejectedBeforeMetadata",
            !verify(newMessage, idpTrust));

        // Publish both trusted signing keys, then wait for all SPs to load.
        stageKeys(idpTrust, Map.of(
            "idp-2025", idpOld.getPublic(),
            "idp-2026", idpNew.getPublic()));
        check("bothSigningKeysPublished", idpTrust.size() == 2);
        check("oldSignatureAcceptedDuringOverlap",
            verify(oldMessage, idpTrust));
        check("newSignatureAcceptedDuringOverlap",
            verify(newMessage, idpTrust));
        check("tamperedSubjectRejected", !verify(
            new SignedAssertion(ISSUER, SP, "mallory",
                newMessage.keyId(), newMessage.signature()), idpTrust));
        check("wrongIssuerRejected", !verify(
            sign("idp-2026", idpNew.getPrivate(),
                "https://fake-idp.example.test", SP, "alice"), idpTrust));
        check("wrongAudienceRejected", !verify(
            sign("idp-2026", idpNew.getPrivate(), ISSUER,
                "https://other-sp.example.test", "alice"), idpTrust));
        check("unapprovedKeyRejected", !verify(
            sign("unapproved", attacker.getPrivate(),
                ISSUER, SP, "alice"), idpTrust));
        check("wrongKeyForTrustedIdRejected", !verify(
            sign("idp-2026", attacker.getPrivate(),
                ISSUER, SP, "alice"), idpTrust));

        // Switch active IdP signer only after consumers acknowledge refresh.
        SignedAssertion afterSwitch = sign("idp-2026",
            idpNew.getPrivate(), ISSUER, SP, "bob");
        check("newSignerAcceptedAfterSwitch",
            verify(afterSwitch, idpTrust));
        check("inFlightOldStillAccepted",
            verify(oldMessage, idpTrust));

        // After cache TTL + in-flight time + confirmed partner cutover.
        stageKeys(idpTrust, Map.of(
            "idp-2026", idpNew.getPublic()));
        check("retiredOldSignerRejected",
            !verify(oldMessage, idpTrust));
        check("newSignerRemainsAccepted",
            verify(afterSwitch, idpTrust));

        // Independent SP encryption-key rotation: receiver retains old key.
        Map<String, PrivateKey> spDecrypt = new HashMap<>();
        spDecrypt.put("sp-dec-2025", spOld.getPrivate());
        EncryptedAssertion encryptedOld = encrypt("sp-dec-2025",
            spOld.getPublic(), "saml-assertion-for-alice");
        EncryptedAssertion encryptedNew = encrypt("sp-dec-2026",
            spNew.getPublic(), "saml-assertion-for-bob");
        check("oldCiphertextDecryptsInitially",
            "saml-assertion-for-alice".equals(
                decrypt(encryptedOld, spDecrypt)));
        check("newCiphertextFailsBeforeNewPrivateKeyInstalled",
            decrypt(encryptedNew, spDecrypt) == null);

        // Install new private key BEFORE telling senders to encrypt to it.
        spDecrypt.put("sp-dec-2026", spNew.getPrivate());
        check("oldCiphertextDecryptsDuringOverlap",
            "saml-assertion-for-alice".equals(
                decrypt(encryptedOld, spDecrypt)));
        check("newCiphertextDecryptsDuringOverlap",
            "saml-assertion-for-bob".equals(
                decrypt(encryptedNew, spDecrypt)));

        byte[] tampered = encryptedNew.ciphertext().clone();
        tampered[0] ^= 1;
        EncryptedAssertion forged = new EncryptedAssertion(
            encryptedNew.recipientKeyId(), encryptedNew.wrappedKey(),
            encryptedNew.iv(), tampered);
        check("tamperedGcmCiphertextRejected",
            decrypt(forged, spDecrypt) == null);

        check("oldAndNewPrivateKeysPresent",
            spDecrypt.size() == 2);
        // Retire old only after all old-encrypted in-flight messages expire.
        spDecrypt.remove("sp-dec-2025");
        check("retiredOldCiphertextUnavailable",
            decrypt(encryptedOld, spDecrypt) == null);
        check("newCiphertextDecryptsAfterRetirement",
            "saml-assertion-for-bob".equals(
                decrypt(encryptedNew, spDecrypt)));

        // Operational gate: metadata propagation is a prerequisite.
        Map<String, Integer> partnerMetadataEpoch = Map.of(
            "sp-a", 7, "sp-b", 6, "sp-c", 7);
        int requiredEpoch = 7;
        check("stalePartnerPreventsUncoordinatedSigningCutover",
            partnerMetadataEpoch.values().stream()
                .anyMatch(epoch -> epoch < requiredEpoch));
        Map<String, Integer> refreshed = Map.of(
            "sp-a", 7, "sp-b", 7, "sp-c", 7);
        check("confirmedPartnersAllowCutover",
            refreshed.values().stream()
                .allMatch(epoch -> epoch >= requiredEpoch));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SamlMetadataRolloverDemo.java
java SamlMetadataRolloverDemo
~~~

**Stdout đã biên dịch/chạy kiểm chứng trên JDK 17:**

~~~text
oldSignatureAcceptedInitially=true
newSignatureRejectedBeforeMetadata=true
bothSigningKeysPublished=true
oldSignatureAcceptedDuringOverlap=true
newSignatureAcceptedDuringOverlap=true
tamperedSubjectRejected=true
wrongIssuerRejected=true
wrongAudienceRejected=true
unapprovedKeyRejected=true
wrongKeyForTrustedIdRejected=true
newSignerAcceptedAfterSwitch=true
inFlightOldStillAccepted=true
retiredOldSignerRejected=true
newSignerRemainsAccepted=true
oldCiphertextDecryptsInitially=true
newCiphertextFailsBeforeNewPrivateKeyInstalled=true
oldCiphertextDecryptsDuringOverlap=true
newCiphertextDecryptsDuringOverlap=true
tamperedGcmCiphertextRejected=true
oldAndNewPrivateKeysPresent=true
retiredOldCiphertextUnavailable=true
newCiphertextDecryptsAfterRetirement=true
stalePartnerPreventsUncoordinatedSigningCutover=true
confirmedPartnersAllowCutover=true
~~~

### 14.1. Phân tích các nhóm kết quả

- **Before publication:** old verification key hợp lệ; new signer chưa tin → **reject**. Đó là hành vi đúng, không phải lỗi.
- **Overlap publication:** khi trust ring **đã được xác minh out-of-band**, SP chấp nhận old/new signer, nhưng chữ ký giả/tamper, sai issuer/audience vẫn bị reject.
- **Activate:** producer dùng new private key, messages mới verify được; old signed messages vẫn có thể được xác minh khi còn chính sách overlap.
- **Retirement:** old signing key bị loại khỏi trust ring → old signature không còn được chấp nhận; new vẫn pass.
- **Decrypt preparation:** new ciphertext chưa thể decrypt trước khi SP cài new private key; sau khi cài both, old/new ciphertext đều decrypt.
- **Decrypt retirement:** old private key không còn → old ciphertext không decrypt được. Điều này chỉ an toàn khi **old in-flight messages đã được xử lý hoặc hết validity**.
- **Operational gate:** một partner còn metadata epoch cũ nghĩa là **chưa được phép cắt signer chung** nếu partner đó critical; sau khi tất cả đạt epoch mới, change gate được mở.

**Demo không thay thế signed SAML metadata, XMLDSig, XML Encryption, HSM integration hoặc giao thức kiểm issuer/conditions**. Chỉ sử dụng để hình dung bất biến của một giai đoạn chồng lấp, còn kiểm production phải chạy Spring/OpenSAML với fixture IdP thật.

## 15. Kiểm thử tích hợp trước cutover

### 15.1. Bốn chiều kiểm thử

| Trạng thái | IdP signs with OLD | IdP signs with NEW | IdP encrypts to OLD SP pub | IdP encrypts to NEW SP pub |
| --- | --- | --- | --- | --- |
| SP hiện tại, chỉ OLD | PASS | FAIL trước staged trust | PASS | FAIL trước new private |
| SP đã pre-stage trust/decrypt cả hai | PASS | PASS | PASS | PASS |
| SP sau switch signer nhưng chưa retire trust/decrypt | PASS | PASS | PASS | PASS |
| SP sau retire OLD | FAIL theo new policy | PASS | FAIL nếu old private removed | PASS |

**Không dùng một test suite cho các chiều ký và mã hóa mà bỏ qua message signature**: ký bằng IdP key, giải mã bằng SP key là **hai phép toán**. Khi thử encrypted assertions cần verify signatures/issuer/audience/recipient/time sau decrypt và đúng XML processing order.

### 15.2. Test cases tối thiểu

| Case | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| S01 | Valid IdP OLD signature trước publish | PASS |
| S02 | Valid IdP NEW signature trước SP refresh | FAIL |
| S03 | Metadata chứa OLD+NEW, được verify | SP trust cả hai |
| S04 | Old signature trong overlap | PASS |
| S05 | New signature trong overlap | PASS |
| S06 | XML signed assertion bị sửa mà không re-sign | FAIL |
| S07 | Forged metadata có attacker's signing key, metadata signature invalid | Metadata **REJECT** |
| S08 | Metadata unsigned khi policy yêu cầu signed | Metadata **REJECT** |
| S09 | Metadata signature mới nhưng anchor chưa được approve | Metadata **REJECT** |
| S10 | Signing key của IdP B dùng cho IdP A | FAIL issuer/trust |
| S11 | Correct key nhưng wrong Audience/Recipient/Destination/InResponseTo | FAIL |
| S12 | Same X509 cert nhưng changed entityID không được approve | FAIL |
| S13 | IdP NEW active, SP old replica chưa refresh | FAIL ở replica cũ → cutover block |
| S14 | SP OLD active signing, IdP chưa tin NEW | PASS với OLD |
| S15 | SP NEW signer trước IdP import NEW | FAIL → cutover block |
| S16 | SP signs NEW khi IdP tin OLD+NEW | PASS |
| E01 | IdP encrypts for SP OLD; SP OLD private installed | PASS |
| E02 | IdP encrypts for SP NEW trước private installation | FAIL |
| E03 | SP has OLD+NEW decrypt keys, IdP encrypts OLD | PASS |
| E04 | SP has OLD+NEW decrypt keys, IdP encrypts NEW | PASS |
| E05 | SP bỏ OLD private trong khi old message còn | FAIL → unsafe retire |
| E06 | Ciphertext integrity/auth tag fail | Decryption FAIL |
| E07 | IdP chọn encryption key khác metadata expectation | Detect + coordinate, không silent fallback |
| M01 | Metadata expired/failed refresh | Fail closed hoặc last-known-good theo approved bounded policy |
| M02 | Metadata XML signature wrong trust anchor | Metadata **REJECT** |
| M03 | Metadata key rollover anchor old/new overlap | Accept đúng signed metadata theo pinned anchors |
| M04 | Metadata bị đổi endpoint/entityID ngoài change | Detect drift, require approval |
| D01 | Multi-pod rollout: mỗi pod có OLD+NEW decrypt | PASS mọi pod |
| D02 | Một pod thiếu NEW private | FAIL ở pod đó → pre-stage incomplete |
| D03 | Browser AuthnRequest pre-cutover, response post-cutover | PASS nếu đúng trust/session |
| D04 | Multiple tenants có IdP key trùng tên alias | Không cross-trust |
| D05 | Rollback active signer về OLD trong overlap | PASS nếu peer còn verify OLD |
| D06 | Rollback decrypt chỉ OLD sau IDP đã encrypt NEW | FAIL → rollback không an toàn |
| D07 | Retire OLD signer sau hết validity/rollback | Old signature FAIL; new PASS |
| D08 | Revocation emergency (private key compromised) | Apply incident response, không giữ compromised key chỉ vì overlap |

### 15.3. Kiểm thử bằng Spring Security thật

Trong test environment được kiểm soát:

1. Tạo **IdP test keys** OLD và NEW, đưa public certs vào trusted metadata và **ký metadata bằng metadata signer độc lập** khi policy yêu cầu.
2. Tạo **SP signing/decryption keys** OLD và NEW; giữ private keys trong test runtime.
3. Bật `saml2Login` và `saml2Metadata`, export SP metadata qua đúng public endpoint.
4. Tạo một AuthnRequest thật bằng `/saml2/authenticate/{registrationId}` và lưu request trong đúng browser/session.
5. Dùng **test IdP/OpenSAML helper** tạo và ký SAMLResponse bằng OLD/NEW IdP private keys; mã hóa cho OLD/NEW SP public certs tương ứng.
6. Gửi fixture qua **actual Spring ACS filter**; đừng dùng test post processor tạo Authentication giả nếu mục tiêu là test XMLDSig/decryption.
7. Assert cả **cryptographic outcome** và các policy guards: issuer, audience, recipient, destination, InResponseTo, conditions, replay, local authority mapping.
8. Khi test negative, không coi session cũ còn Authentication là callback mới thành công; assert **không có new principal/role assignment**.
9. Test một browser có AuthnRequest từ trước cutover, SAMLResponse trở về sau cutover.
10. Test callback đến mọi pod/node và token/session store nếu dùng distributed request repository.
11. Thử refresh metadata qua cache/federation/CDN trong staging; không dựa vào restart của một pod duy nhất.
12. Sau retirement, xác nhận old-only signatures bị reject và old encrypted payload không còn là traffic hợp lệ.

**Quan trọng:** thay certificate trong XML sau khi đã ký tạo **signature failure giả**, không chứng minh rotation trust ring đúng. Để test old/new signing credentials, phải tạo **signed fixtures hợp lệ** bằng private key tương ứng trước khi gửi Spring ACS.

## 16. Quan sát tiến trình rollout và chẩn đoán

### 16.1. Log/metrics có giá trị

Nên log ở mức **không chứa raw SAMLResponse, private keys, assertions hoặc session IDs**:

~~~text
event=SAML_METADATA_REFRESH
registrationId=corp
expectedIssuer=https://idp.example.test/saml
metadataSource=approved-idp-endpoint
metadataVersion=rollover-7
signatureValidated=true
trustedSigningKeyCount=2
metadataFresh=true
traceId=trace-7a12
~~~

~~~text
event=SAML_SIGNING_KEY_ROLLOVER
registrationId=corp
phase=ACTIVATE
activeSignerFingerprint=sha256:...
acceptedVerificationKeys=2
partnersAcknowledged=3
partnersRequired=3
traceId=trace-7b34
~~~

~~~text
event=SAML_DECRYPT_FAILURE
registrationId=corp
reason=NO_MATCHING_PRIVATE_KEY
credentialVersion=rollover-7
metadataVersion=rollover-7
node=auth-pod-3
traceId=trace-7c56
~~~

Các giá trị hash/fingerprint ở đây là **mẫu log minh họa**, không phải fingerprints thật. Với đối tác nhạy cảm, có thể log short **approved key alias** thay raw issuer URL; tránh log PII. Không log raw `ds:KeyInfo` khi nó chứa dữ liệu nhạy cảm ngoài public cert.

Metric hữu ích:

- `saml_metadata_refresh_success_total`, `saml_metadata_refresh_failure_total`.
- `saml_metadata_age_seconds`, `saml_metadata_remaining_validity_seconds`.
- `saml_trusted_signing_keys_count` theo registration.
- `saml_response_signature_reject_total` theo safe reason category.
- `saml_decrypt_failure_total` theo registration/node.
- `saml_authn_success_total` và `saml_authn_failure_total` theo IdP/registration.
- `saml_active_signing_key_generation` hoặc deployment epoch.
- `saml_partner_ack_remaining` trong change dashboard.
- `saml_rollover_phase` (P0–P5) và rollback readiness flag.
- `saml_assertion_replay_reject_total`: monitor độc lập, không bỏ replay validator khi quay key.
- `saml_cert_expiry_days` chỉ như observability của certificate file; không đồng nhất với metadata trust/freshness.

**Không dùng full certificate Base64, private key, NameID, ticket, SAMLResponse hoặc session cookie làm metric labels/log fields**.

### 16.2. Nguyên nhân lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra và khắc phục |
| --- | --- | --- |
| Signatures NEW bị reject, OLD vẫn pass | IdP switched trước khi SP tải new cert | Refresh trusted metadata; block cutover |
| Signature rejects chỉ ở vài pods | Rolling deploy chưa đồng bộ verification ring | Kiểm từng pod/repository and restart/reload |
| IdP metadata fetch OK nhưng XML metadata không được verify | Metadata repository không có verificationCredentials | Cấu hình independent anchor; kiểm signature policy |
| Metadata signer mới bị reject | Metadata trust anchor M_NEW chưa pre-stage | Out-of-band metadata signer rotation |
| Certificate đúng nhưng issuer sai | EntityID/tenant/registration drift | Fix issuer/registration mapping |
| Cert NotAfter qua ngày nhưng login vẫn pass | SAML direct metadata key trust khác browser PKIX | Review org policy; không suy runtime là tự an toàn |
| Signed SAMLResponse đúng cert mà fail | Audience/Recipient/Destination/InResponseTo/time/replay | Không tắt security validators |
| EncryptedAssertion fail sau publish SP metadata | IdP chọn new pub nhưng một SP pod thiếu new private | Pre-stage decryption key mọi replicas |
| EncryptedAssertion fail sau remove OLD | IdP còn gửi old encrypted messages | Khôi phục old decrypt trong approved overlap nếu chưa compromised |
| Metadata endpoint SP có old only | Metadata resolver/cache chưa nhận config | Fetch public endpoint, compare fingerprint |
| IdP không tự refresh metadata | Vendor cần manual import/restart | Xác nhận theo vendor + evidence |
| Client IdP chọn OLD dù NEW được publish | Sender encryption selection không như tưởng tượng | Vendor behavior, explicit coordination |
| Login fail chỉ sau load balancer | public/internal ACS khác, forwarded headers | Fix trusted proxy public URL |
| Keys trong PEM không khớp cert | Secret alias mount sai/version trộn | Compare SPKI pubkey digest |
| Metadata refresh mất nguồn | Network/DNS/TLS/expired cache | Last-known-good within approved bounded policy; alert |
| JWKS đổi nhưng bài toán đang SAML | Dùng nhầm giao thức/endpoint | Phân biệt SAML XML metadata và OIDC JWKS |
| Metadata bị giả nhưng được nhận | Không có bootstrap provenance/signature trust | Incident; restore approved trust anchors |
| Rollback sau retirement làm fail old sign | Consumers đã bỏ old | Không rollback một bước; dùng staged trust update |
| TLS certificate rotation gây lỗi metadata fetch | HTTPS trust chain/hostname lỗi | Sửa TLS trust, không import untrusted XML |
| KMS/HSM key không export được | Code giả định PrivateKey PEM file | Dùng provider/PKCS#11 integration và tests |
| Runtime secret volume đã đổi nhưng behavior cũ | Beans đã cache credentials | Restart/reload repository theo explicit plan |
| Metadata gồm nhiều KeyDescriptors nhưng một consumer reject | Đối tác không hỗ trợ multi-key role | Thỏa thuận vendor-specific migration |

## 17. Runbook làm việc giữa các nhóm

### 17.1. Thông tin mỗi bên phải giao

**Bên IdP gửi cho SP:**

- IdP entityID và SSO/SLO endpoints **không đổi** nếu chỉ rotate cert.
- Metadata XML signed/verified location hoặc signed file.
- Old/new signing public cert **SHA-256 fingerprints** xác nhận out-of-band.
- Metadata signer trust anchor version và TTL/validUntil.
- Thời điểm dự kiến IdP chuyển active signing key.
- Cách canary/test signing cert mới; liên hệ rollback.
- Xác nhận có giữ old signing key trong overlap và deadline retire.

**Bên SP gửi cho IdP:**

- SP entityID/registrationId, public ACS/SLO URLs.
- Old/new SP signing public cert và ngày active switch (nếu SP rotates signer).
- Old/new SP encryption public cert cùng khả năng SP decrypt bằng old+new.
- Metadata endpoint/signed metadata checksum/version, refresh/import instructions.
- Cách IdP chọn encryption key; có hỗ trợ multi-key metadata không.
- Acknowledgment SP pods đã staged private key/verification ring.
- Rollback policy, stop conditions, monitoring.

### 17.2. Quy trình approval và handshake

~~~text
Change owner -> mở key rotation change request
Security     -> approve key sizes, algorithms, metadata signer provenance
Key owner    -> generate new key, protect private material
Metadata pub -> publish OLD + NEW through signed/trusted channel
Peer operator-> refresh/import; verify expected entityID + fingerprints
Peer operator-> confirm "ACCEPTS NEW, STILL ACCEPTS OLD"
Change owner -> check ALL critical peers acknowledged
Change owner -> authorize cutover active signer / encryption sender
On-call      -> run canary + synthetic SAML flow tests
On-call      -> observe errors and session/user login outcomes
Change owner -> mark stable after overlap and rollback window
Key owner    -> remove OLD from metadata/runtime safely
Security     -> verify retirement and audit close-out
~~~

Nếu peer không phản hồi, không tự suy “metadata đã publish nên chắc peer biết”. Có thể phân đối tác critical/noncritical theo SLA, nhưng quyết định bỏ một đối tác phải là **approved risk/business decision**, không phải implicit timeout.

## 18. Emergency rotation khác planned rotation

**Planned rotation** giả định private OLD còn an toàn; giữ OLD trong overlap để tránh downtime.

**Emergency rotation** xảy ra khi:

- Private signing key bị lộ, có thể bị attacker ký giả SAMLResponse.
- SP decrypt private key bị đánh cắp, encrypted assertions có nguy cơ bị đọc.
- Metadata signer key bị compromise, attacker có thể phân phối metadata giả.
- Secret store/HSM bị breach hoặc key custody không còn đáng tin.

Khi đó:

1. Kích hoạt incident response và **ngưng tin/thu hồi khóa bị compromise theo mức nguy hiểm**, dù gây outage.
2. Không giữ compromised key tin cậy cho đến hết cache TTL chỉ để giữ availability.
3. Phát keys mới qua **independently authenticated emergency channel**.
4. Nhanh chóng thay metadata signing anchors, IdP verification certs/SP encryption keys và revoke sessions/tokens nếu threat model yêu cầu.
5. Rà soát logs về forged assertions, metadata substitution, data exposure, login under wrong identity.
6. Với decryption key bị lộ, cần đánh giá **past ciphertext exposure**; việc quay key mới không làm dữ liệu đã mã hóa bằng old key trở nên bí mật trở lại.
7. Chọn recovery/rollback strategy **không đưa lại compromised key**.
8. Ghi change exception và post-incident corrective actions.

**Chồng lấp chỉ là chiến lược availability khi OLD key còn đáng tin.** Nó không phải quy tắc an toàn để trì hoãn phản ứng với compromise.

## 19. Phân biệt SAML, OIDC JWKS và TLS trong vận hành

| Hệ thống | Producer metadata | Tập public keys | Token/message | Điều không được nhầm |
| --- | --- | --- | --- | --- |
| **SAML IdP** | `EntityDescriptor/IDPSSODescriptor` | `KeyDescriptor use="signing"` | XMLDSig trên Response/Assertion | Không tin cert chỉ vì nó ở `KeyInfo` untrusted |
| **SAML SP** | `SPSSODescriptor` | Signing/encryption KeyDescriptors | Signed AuthnRequest, EncryptedAssertion recipient | Không gửi private SP keys cho IdP |
| **SAML metadata signer** | Federation/operator | Independent metadata verification anchor | Signed metadata XML | Khác IdP assertion signing key |
| **OIDC Provider** | OpenID configuration + JWKS | JWKs/kid của issuer | JWT ID Token/access token theo profile | Không so SAML EntityID với OIDC issuer tùy ý |
| **HTTPS server** | TLS certificate chain | Trust anchors của TLS client | HTTP/TLS connection | HTTPS trust không đồng nghĩa metadata XML signature validation |
| **CAS Server** | Registered service/ticket infrastructure | Service-specific trust mechanisms | Single-use Service Ticket | ST không phải signed SAML/JWT; không dùng SAML KeyDescriptor |

Trong OIDC JWKS rollover, pattern thường là **publish new JWK/kid trước, chuyển signer, giữ old JWK tới khi all issued JWTs hết hiệu lực + cache TTL**, sau đó retire. Nhưng JWKS signature verification và SAML XMLDSig có token/library/attack surface khác, nên phải test riêng.

## 20. FAQ / tự kiểm tra

**1. Khi IdP đổi signing key, bên nào tạo private key mới?**

**IdP**. SP chỉ cần **public signing certificate** của IdP được lấy từ trusted metadata/config.

**2. SP có thể tự nhận IdP signing certificate mới từ SAMLResponse/KeyInfo không?**

Không. `KeyInfo` có thể chỉ dẫn candidate, nhưng public key để verify phải được **tin từ metadata/config có provenance hợp lệ**, không tự tin certificate do message đưa tới.

**3. Vì sao phải công bố public signing key NEW trước khi dùng private NEW?**

Vì consumers/SP cần nạp trust ring chứa NEW trước; nếu chưa có, new signatures sẽ bị từ chối.

**4. Có cần SP ký một AuthnRequest bằng cả hai private signing keys không?**

Không theo quy trình phổ biến. SP chọn một active signer; **IdP verify được cả OLD và NEW** trong overlap. Behavior multi-signatures phải theo protocol/product support riêng.

**5. Vì sao SP decryption key rotation phải cài private NEW trước khi public NEW lên metadata?**

Vì IdP có thể chọn NEW để mã hóa ngay sau khi refresh; SP phải giải mã được.

**6. Khi IdP đã chuyển encrypt sang NEW, có thể xóa private OLD ngay?**

Không nên nếu còn encrypted messages cũ in-flight hoặc rollback window. Giữ OLD theo plan cho đến retire an toàn.

**7. Việc KeyDescriptor OLD+NEW xuất hiện trong metadata có bắt buộc IdP chọn NEW không?**

Không. Algorithm/key selection có thể phụ thuộc implementation/vendor; phải phối hợp và test.

**8. Metadata XML signature và SAMLResponse XML signature có cùng trust anchor không?**

Không mặc nhiên. Metadata trust phải được bootstrap độc lập; IdP assertion verification keys lấy từ trusted IdP metadata sau khi được chấp nhận.

**9. `fromTrustedMetadataLocation` có tự động kiểm XML metadata signature không?**

Không nên suy như vậy. Spring Security 7.x docs nói **metadata signature validation được thực hiện khi cung cấp verification credentials** cho repository; thiếu credentials thì component không validate metadata signature. Trust qua nguồn đã duyệt/TLS là mô hình riêng.

**10. Vì sao metadata refresh success không chứng minh runtime đã dùng new key?**

Vì Spring bean/cache/repositories/replicas có thể chưa reload hoặc không map vào active `RelyingPartyRegistration`. Cần test signature verification trên từng pod/registration.

**11. Certificate SAML hết NotAfter có chắc chắn bị framework reject không?**

Không thể khẳng định chung. Trong metadata direct trust, X.509 có thể chỉ là public-key carrier; cần kiểm policy của framework/IdP và tổ chức, không suy từ PKIX browser TLS.

**12. Nếu new signer hoạt động nhưng app vẫn báo Audience mismatch, có phải key rollover fail không?**

Không nhất thiết. Signature đã pass nhưng **SAML semantic validation** có vấn đề khác. Giữ issuer/audience/recipient/InResponseTo checks, không tắt chúng để “sửa cert”.

**13. Rollback sau khi SP đã nhận encrypted NEW có thể chỉ phục hồi OLD deployment không?**

Không an toàn nếu rollback làm mất private NEW. Trong overlap rollback phải vẫn decrypt **OLD+NEW**.

**14. Bao lâu mới retire OLD?**

Sau khi partners đã acknowledge refresh, metadata cache/propagation/in-flight/clock skew và rollback window đã được kiểm, không dựa vào một số ngày cố định.

**15. Nếu đối tác chỉ cho một certificate thì sao?**

Không thể giả định key overlap tự hoạt động. Phải có vendor-specific migration/maintenance plan, hoặc điều phối cutover/trust theo hỗ trợ thực tế.

**16. Có nên dùng certificate fingerprint tự tải từ IdP URL làm bằng chứng danh tính?**

Không nếu fingerprint và cert đều từ cùng một kênh bị xâm nhập. Cần **out-of-band confirmation** hoặc chữ ký metadata được xác minh bởi trust anchor có trước.

**17. Có thể giữ old compromised key để tránh gián đoạn không?**

Không theo quy tắc normal overlap. Khi key bị lộ, phải ưu tiên incident response và ngăn forged identities.

**18. Vì sao test phải gồm cả OLD và NEW?**

Để chắc rằng **overlap đúng nghĩa**, không phải producer switched NEW trong khi consumers vừa xóa OLD hoặc chưa nhận NEW.

## 21. Checklist triển khai chuẩn

- [ ] Đã inventory SP/IdP entityIDs, registrations, owners và cả hai hướng metadata.
- [ ] Đã xác định mục đích khóa: assertion signing, AuthnRequest signing, SP decryption, metadata signing hoặc TLS.
- [ ] Đã có planned maintenance/change record với phê duyệt security/operations và contact đối tác.
- [ ] Private NEW key được tạo bằng CSPRNG/HSM/KMS và bảo vệ đúng scope; private key không bao giờ đưa vào metadata.
- [ ] Public certificate/fingerprint NEW được xác nhận qua kênh độc lập.
- [ ] Metadata được fetch/import qua verified trust model; nếu policy yêu cầu signed metadata, metadata signature được xác minh.
- [ ] Metadata signer trust anchor mới đã được bootstrap độc lập nếu metadata signer cũng rotate.
- [ ] Metadata `entityID`, SSO/ACS/SLO URLs, binding và tenant scope không bị đổi ngoài kế hoạch.
- [ ] Metadata `KeyDescriptor use`/certificate serial/fingerprint đúng cả OLD và NEW.
- [ ] Metadata validUntil/cacheDuration/HTTP cache/federation aggregator và partner refresh SLAs được ghi nhận.
- [ ] Tất cả consumer critical đã nạp OLD+NEW verification keys trước active signer switch.
- [ ] Tất cả SP nodes đã cài private OLD+NEW decryption keys trước khi IdP được phép encrypt NEW.
- [ ] IdP hiểu key selection khi có multi-key encryption metadata; đã canary sender behavior.
- [ ] Outbound SP signing credential active được chọn rõ; IdP tin cả OLD+NEW signing public keys trong overlap.
- [ ] File private key/certificate pair được kiểm SPKI public digest/role/permission và secrets mount.
- [ ] Spring Security `RelyingPartyRegistration` thực nhận đúng credentials theo từng registration.
- [ ] Spring metadata repository có refresh/expiry-aware behavior đúng; khi dùng signed metadata có verificationCredentials độc lập.
- [ ] Có kiểm chứng runtime **thật** trên mọi nodes, không chỉ staging hay một pod canary.
- [ ] SAML signature, decryption, issuer, audience, recipient, destination, InResponseTo, time, replay vẫn được kiểm.
- [ ] Signed+encrypted response fixture OLD/NEW đều pass trong overlap; tampered/untrusted credentials fail.
- [ ] Không dùng test postprocessor dựng Authentication giả để tuyên bố crypto validation pass.
- [ ] Browser SSO flow qua multiple nodes/regions vẫn giữ AuthnRequest correlation.
- [ ] Cửa sổ overlap >= cache/propagation/in-flight/clock skew/rollback budget theo policy.
- [ ] Có metrics metadata refresh, key activation, unknown signer, decrypt fail, login failure per registration.
- [ ] Logs không có private keys, SAMLResponse/Assertion/NameID/session cookies hoặc raw secrets.
- [ ] Rollback giữ được cả old/new decrypt keys và không phục hồi compromised private key.
- [ ] Retire OLD chỉ khi đối tác xác nhận, in-flight/rollback window kết thúc và không còn traffic dùng OLD hợp lệ.
- [ ] Sau retirement, OLD-only signed message bị reject; new message pass; old ciphertext không cần nữa.
- [ ] Emergency compromise response khác planned rollover; có revoke/notification runbook.
- [ ] Chỉ các ô trạng thái/triển khai nghiệp vụ được cập nhật theo change approval; không trộn key rotation với migration entityID/ACS ngoài phạm vi.
- [ ] Đã có post-change report: fingerprints, epochs, owner sign-off, tests, timings và rollback outcome.

## 22. Tài liệu chính thức và đọc thêm

- Spring Security, **Saml 2.0 Metadata**: parse/publication, metadata repository, expiry-aware refresh, metadata signature verification và endpoint `/saml2/metadata`: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security, **SAML 2.0 Login Overview**: `RelyingPartyRegistration`, verification/signing/decryption credentials và thực hiện Web Browser SSO: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **Authenticating SAML Responses**: `OpenSaml5AuthenticationProvider`, signature/decryption/issuer/conditions validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Producing AuthnRequests**: signing private key của SP, algorithms và request signing: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Boot, **SAML 2.0 Relying Party auto-configuration**: `signing.credentials`, `decryption.credentials` và `assertingparty.verification.credentials`: https://docs.spring.io/spring-boot/reference/security/saml2.html
- OASIS, **SAML V2.0 Metadata Interoperability Profile**: trusted metadata, key rollover, metadata keys as public-key carriers, metadata validity/caching: https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop.html
- OASIS, **SAML 2.0 Metadata specification**: `EntityDescriptor`, `KeyDescriptor`, `validUntil` và metadata signatures: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS, **SAML 2.0 Core**: signature/subject/conditions, encrypted assertions, issuer/audience/time: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- Shibboleth historical note, **IdPKeyRollover**: publish new signing key in metadata, wait propagation, then switch signer and retire old key (tài liệu dành cho Shibboleth 2 đã EOL; quy trình nguyên tắc vẫn hữu ích): https://shibboleth.atlassian.net/wiki/spaces/SHIB2/pages/2577072227/IdPKeyRollover
- OWASP, **Cryptographic Storage Cheat Sheet**: key lifecycle, least privilege và secure cryptographic storage: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP, **SAML Security Cheat Sheet**: signature verification, trusted metadata, audience, recipient, InResponseTo và replay controls: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- Kubernetes, **Secrets**: volume/config update và access control: https://kubernetes.io/docs/concepts/configuration/secret/

**Kết luận:** muốn luân chuyển khóa SAML 2.0 **không gián đoạn**, phải biết bên nào **ký**, bên nào **verify**, bên nào **encrypt**, bên nào **decrypt** và **nguồn metadata đã được tin cậy bằng cách nào**. Với signing, **publish public NEW → consumers trust OLD+NEW → activate private NEW → retire OLD**. Với SP decryption, **install private NEW trong khi giữ OLD → publish encryption public NEW → IdP switch encrypt NEW → giữ decrypt OLD+NEW → retire OLD**. Giai đoạn overlap phải bao phủ **cache refresh, partners, in-flight messages, nhiều pods và rollback**; metadata signer trust là một ranh giới độc lập. Đừng tắt signature/metadata/replay validation để vượt qua lỗi rotation, và đừng giữ key đã bị compromise chỉ để duy trì dịch vụ.