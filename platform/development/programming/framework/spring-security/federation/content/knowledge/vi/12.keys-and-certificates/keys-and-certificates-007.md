# Luân chuyển chứng thư ký của IdP với giai đoạn chấp nhận đồng thời nhiều khóa

> **Chủ đề:** Spring Security – federation. **Nhóm:** Khóa và chứng thư. Bài hướng dẫn Service Provider (SP/Relying Party) duy trì SAML 2.0 Single Sign-On khi Identity Provider (IdP/Asserting Party) **đổi khóa ký** mà không gián đoạn đăng nhập, bằng cách triển khai một giai đoạn **tin cậy đồng thời khóa cũ và khóa mới** đã được xác minh. Ví dụ dành cho Java 17+, Spring Boot và Spring Security SAML2 Web Browser SSO.

## 1. Mục tiêu và ranh giới bài học

Kết thúc bài, bạn có thể:

1. Phân biệt **IdP signing certificate**, **SP signing certificate**, **SP decryption private key**, **metadata signing key** và **TLS certificate**; hiểu khóa nào phải luân chuyển và ai sở hữu khóa bí mật.
2. Giải thích tại sao đổi IdP signing certificate “một phát” dễ làm toàn bộ SP bị từ chối SAMLResponse, dù user đã đăng nhập thành công tại IdP.
3. Thiết kế lịch **prepublish → dual trust → IdP switch → observe → retire old key** có thời hạn, owner, bằng chứng QA và rollback.
4. Khai báo **hai chứng thư công khai** của cùng một IdP trong `RelyingPartyRegistration` / `assertingparty.verification.credentials` của Spring Security.
5. Dùng metadata đáng tin để làm mới tập signing certificates; hiểu giới hạn của cached/refreshable metadata và chữ ký của chính metadata.
6. Kiểm thử SAMLResponse được ký bởi từng khóa ở mỗi giai đoạn, gồm các ca sai issuer, audience, recipient, expired assertion, khóa lạ, chứng thư/metadata chưa phê duyệt và đa tenant.
7. Xử lý riêng tình huống **luân chuyển có kế hoạch** và **nghi lộ private key**; biết khi nào cần bỏ overlap để chặn khóa cũ ngay.
8. Xác nhận cuối cùng rằng ứng dụng đã **loại khóa cũ khỏi danh sách được tin**, không chỉ ngừng dùng nó ở IdP.

**Kết luận trước:** **Overlap chỉ dành cho những khóa công khai thuộc IdP được tin và đã được duyệt**. Nó không có nghĩa “chấp nhận mọi certificate IdP gửi trong bản tin” hay “bỏ xác minh chữ ký SAML để tránh downtime”.

## 2. Ngữ cảnh: một IdP, nhiều SP và khóa ký đang được thay

Giả sử doanh nghiệp có IdP SAML với:

| Giá trị | Ví dụ minh họa | Vai trò |
| --- | --- | --- |
| IdP `entityID` | `https://sso.partner.example/issuer` | Định danh logic của bên phát hành |
| IdP SSO endpoint | `https://sso.partner.example/saml/sso` | Nơi browser chuyển `AuthnRequest` đến |
| SP `registrationId` | `partner` | Khóa tra cứu nội bộ trong Spring Security |
| SP `entityID` | `https://app.example.org/saml2/service-provider-metadata/partner` | Audience của assertion dành cho SP |
| SP Assertion Consumer Service | `https://app.example.org/login/saml2/sso/partner` | Đích nhận SAMLResponse trên SP |
| Khóa ký IdP hiện tại | `K_old`, chứng thư công khai `C_old` | Đang ký SAMLResponse/Assertion |
| Khóa ký IdP sắp dùng | `K_new`, chứng thư công khai `C_new` | Sẽ trở thành khóa ký chính |
| Verification trust set ở SP | `{C_old}` → `{C_old,C_new}` → `{C_new}` | Định nghĩa khóa công khai SP cho phép xác minh |

**IdP giữ private key `K_old`/`K_new`.** SP chỉ cần các **public X.509 certificates `C_old` và `C_new`** để xác minh chữ ký. SP **không bao giờ** cần biết private signing key của IdP. Ngược lại, nếu SP tự ký AuthnRequest hoặc giải mã EncryptedAssertion thì đó là bộ khóa **SP sở hữu**, có lịch đổi và yêu cầu phối hợp khác.

### 2.1. Những lớp “chứng thư” không được nhầm

| Loại | Chủ sở hữu private key | SP dùng thế nào? | Đổi một loại có buộc đổi loại kia không? |
| --- | --- | --- | --- |
| **IdP SAML signing certificate** | IdP | Xác minh XML Signature trên Response/Assertion và các bản tin SAML được ký | Không tự động |
| **IdP metadata signing certificate** | IdP/federation operator | Xác minh chữ ký **tài liệu metadata** trước khi nhập các khóa ký SAML | Không tự động; trust anchor phải độc lập |
| **IdP TLS server certificate** | IdP/web ingress | Thiết lập HTTPS khi browser/SP truy cập IdP | Không thay cho SAML signature verification |
| **SP AuthnRequest signing certificate** | SP | SP dùng private key để ký AuthnRequest gửi IdP | Không giống IdP signing certificate |
| **SP decryption certificate** | SP | IdP mã hóa assertion cho SP, SP dùng private key giải mã | Có thể cần double-decryption khi luân chuyển SP key; khác bài này |
| **SP TLS server certificate** | SP/web ingress | Bảo vệ ACS và phiên browser HTTPS | Không liên quan trực tiếp khóa SAML ký của IdP |

**Nguyên tắc:** Chứng thư IdP ký SAML có thể xuất hiện trong metadata dưới `<KeyDescriptor use="signing">`; public key được tin để xác minh chữ ký. Chứng thư trong HTTPS chain hoặc `<ds:KeyInfo>` của một SAMLResponse **không tự trở thành trust anchor**. Chỉ đưa một certificate vào trust set sau khi xác thực nguồn và quyền thay đổi cấu hình federation.

### 2.2. Xác minh chữ ký chỉ là một điều kiện

Ngay cả khi chữ ký xác minh thành công bằng `C_old` hoặc `C_new`, SP vẫn phải xác minh:

- IdP `Issuer` đúng đăng ký đã phê duyệt.
- `AudienceRestriction` chứa đúng SP `entityID`.
- `SubjectConfirmationData/@Recipient` và `Response/@Destination` phù hợp ACS HTTPS.
- `InResponseTo` khớp AuthnRequest trong SP-initiated flow, chống replay và ràng buộc phiên.
- `Conditions/NotBefore/NotOnOrAfter` và bearer confirmation time còn hợp lệ, với clock skew nhỏ có kiểm soát.
- Status, đúng phần message/assertion được ký, không XML signature wrapping, đúng profile/binding.
- Quyền trong app vẫn là authorization sau khi xác thực; khóa ký hợp lệ **không cấp `ROLE_ADMIN`**.

**Không thay đổi các validator khác** chỉ để “đổi certificate cho trơn tru”.

## 3. Luồng sự cố khi đổi khóa không có overlap

Kịch bản sai:

```text
Trước T1:
  IdP ký bằng K_old
  SP chỉ tin C_old
  => SAML login thành công

Tại T1:
  IdP ngay lập tức chuyển sang ký bằng K_new
  SP chưa được cập nhật, chỉ tin C_old
  => SAMLResponse từ K_new bị từ chối (signature verification failure)

Tại T2:
  Một số SP/node đã tin C_new nhưng các node khác vẫn tin C_old
  => Đăng nhập chập chờn theo load balancer / tenant / pod

Tại T3:
  SP xóa C_old trong khi IdP vẫn còn phát message cũ
  => Một số response đang bay hoặc SLO message có thể bị từ chối
```

Chỉ nhìn thấy trình duyệt quay về login page không đủ để xác định nguyên nhân: cần phân biệt **IdP xác thực user** thành công với **SP xác minh SAMLResponse** thành công. Các message lỗi như “signature validation failed”, “unknown signing certificate” hoặc lỗi trust metadata có thể xuất hiện ở component khác nhau, tùy framework và cấu hình log.

SAMLResponse đã bị từ chối không trở thành hợp lệ bằng cách tăng session timeout hay mở `permitAll("/**")`. Lỗi nằm ở quan hệ tin cậy của khóa/issuer/cert, không phải URL authorization.

## 4. Quy trình luân chuyển không gián đoạn: prepublish → overlap → switch → retire

### 4.1. Mô hình trạng thái chuẩn

```text
Phase 0: STEADY
  IdP signs:          K_old
  SP trusts:          {C_old}

         |
         | IdP tạo K_new; public C_new được phê duyệt/phân phối
         v

Phase 1: PREPARED / DUAL TRUST
  IdP signs:          K_old
  SP trusts:          {C_old, C_new}

         |
         | Xác minh mọi SP, mọi pod/region/tenant đã áp dụng
         v

Phase 2: SWITCHED / OBSERVING
  IdP signs:          K_new
  SP trusts:          {C_old, C_new}

         |
         | Đợi message in-flight, cache TTL, cửa sổ rollback;
         | xác nhận không còn message hợp lệ từ K_old
         v

Phase 3: RETIRED
  IdP signs:          K_new
  SP trusts:          {C_new}
  K_old:              IdP không dùng; private key cũ hủy/khóa theo policy
```

Đây là **chiến lược trust overlap**: trong Phase 1 và Phase 2, SP chỉ mở rộng **tập khóa công khai được chấp nhận cho cùng một IdP**, không mở rộng issuer, tenant, ACS hay quyền ứng dụng. Một assertion được ký bởi bất kỳ khóa nào trong tập **vẫn phải** vượt qua tất cả kiểm tra SAML khác.

### 4.2. Từng bước triển khai

**Bước 0 — Kiểm kê và chốt hợp đồng.** Liệt kê các SP/tenant/cluster đang kết nối IdP; xác định certificate hiện tại, fingerprint SHA-256, thời hạn `NotBefore/NotAfter`, thuật toán/độ dài khóa, đường lấy metadata, TTL cache, owner của IdP và từng SP, khả năng refresh cấu hình và rollback. Ghi thời điểm IdP dự kiến chuyển signing key và ngày cuối cùng có thể dùng khóa cũ. Không giả định một SP bất kỳ tự động refresh metadata.

**Bước 1 — Tạo khóa mới ở IdP.** IdP sinh private key mới qua HSM/secret manager/quy trình quản trị phù hợp, xác lập quyền sử dụng, thuật toán chữ ký được policy chấp nhận, và xuất **chỉ public certificate**. Chứng thư mới phải gắn với đúng IdP `entityID` và kênh phân phối được phê duyệt; không gửi private key cho SP.

**Bước 2 — Công bố đồng thời chứng thư cũ và mới.** Trong IdP metadata, công bố hai public signing certificate (tùy sản phẩm), hoặc cung cấp gói certificate đã được xác thực qua kênh kiểm soát thay đổi. Giữ nguyên `entityID` và SSO URL trừ khi đó là **thay đổi riêng** có phê duyệt. Nếu metadata ký, metadata mới phải có chữ ký hợp lệ từ metadata signing trust anchor đã biết.

**Bước 3 — SP nạp C_new trong khi vẫn chấp nhận C_old.** Spring Security có thể khai báo nhiều `verification.credentials` cho cùng IdP. Đẩy cấu hình tới tất cả node, kiểm tra cấu hình *hiệu lực* (không chỉ file dự kiến), refresh cache/repository theo quy trình và tạo smoke tests.

**Bước 4 — Xác minh dual trust đã hoạt động thực sự.** Với IdP test hoặc môi trường kiểm thử được kiểm soát, phát SAMLResponse ký bằng `K_old` và `K_new`; cả hai phải được SP chấp nhận **nếu issuer/audience/recipient/time/correlation đều đúng**. Response từ khóa lạ phải bị từ chối. Nếu một node/region chưa có C_new, **chưa chuyển IdP**.

**Bước 5 — IdP chuyển ký message mới bằng K_new.** Chỉ thực hiện sau khi có đủ bằng chứng mọi SP sẵn sàng. Theo dõi lỗi xác thực, tỷ lệ login thành công và dấu hiệu metadata refresh/clock drift. IdP có thể giữ C_old trong metadata trong giai đoạn này nhưng **không tiếp tục tạo message mới bằng K_old** trừ khi đang rollback có kiểm soát.

**Bước 6 — Giữ overlap có giới hạn.** Duy trì `{C_old,C_new}` trong một khoảng được phê duyệt để xử lý in-flight SAMLResponse, session/SSO/logout messages còn ký bằng khóa cũ (nếu có), cache TTL, phân phối cấu hình, cũng như cửa sổ rollback. Thời gian không được chọn tùy tiện; xem mục 4.3.

**Bước 7 — Loại C_old khỏi mọi SP.** Xác nhận IdP không còn dùng `K_old`, không còn các bản tin hợp lệ cần xác minh bằng C_old và cửa sổ rollback đã kết thúc. Cập nhật metadata/trust store thành `{C_new}`, đẩy tới toàn bộ node/tenant, làm test âm với chữ ký cũ, và kiểm tra cache/remote metadata không tự đưa C_old trở lại.

**Bước 8 — Đóng thay đổi và thu hồi khóa cũ.** IdP khóa/hủy/archive private key K_old theo chính sách và ghi evidence của trust-set cuối cùng; SP đóng incident/change ticket, giao lại giám sát chứng thư mới, lên lịch vòng quay tiếp theo.

### 4.3. Bao lâu thì giữ hai khóa?

**Không có con số overlap cố định dùng cho mọi IdP/SP.** Cần xem xét:

- Thời gian rollout cấu hình SP ở tất cả node, region, tenant và phiên bản ứng dụng.
- TTL của metadata, thời gian refresh theo lịch, ETag/cache và cơ chế retry khi IdP metadata unavailable.
- Độ dài tối đa mà assertion/Response hợp lệ theo SAML, `NotOnOrAfter` và clock skew (cùng với thời gian message in-flight).
- Các SAML Single Logout/Artifact/luồng khác còn dùng signing key cũ (nếu nằm trong scope).
- Mốc certificate validity, có đủ thời gian trước expiry hay không.
- Cửa sổ IdP rollback còn được phép và khả năng khôi phục an toàn.
- Cảnh báo/metrics thực tế chứng minh không còn message mới ký bằng K_old sau cutover.

Chẳng hạn: nếu metadata refresh 24 giờ một lần, SP rollout tối đa 2 ngày và có nhiều node không đồng bộ, overlap tính theo vài phút là thiếu cơ sở. Nhưng việc giữ C_old vô thời hạn cũng làm **kéo dài cửa sổ chấp nhận khóa cũ**, đặc biệt nguy hiểm nếu khóa đã yếu hoặc có nguy cơ lộ. Chọn thời lượng theo rủi ro và **đặt deadline rõ ràng**, không “giữ hai khóa cho chắc mãi mãi”.

**Tách hai khoảng thời gian:** prepublication lead time (trước khi IdP ký bằng K_new) và post-switch grace period (sau khi IdP chuyển). Không thể gộp hai khoảng vì mục tiêu khác nhau.

## 5. Làm thế nào SP biết hai certificate đều thuộc IdP hợp lệ?

### 5.1. Metadata đúng issuer và certificate có nguồn tin cậy

Một `EntityDescriptor` metadata của IdP có `entityID` và một `IDPSSODescriptor`. Trong giai đoạn overlap có thể có hai `KeyDescriptor use="signing"`, mỗi phần tử công bố một public certificate. Hình dạng XML rút gọn để minh họa quan hệ:

```xml
<md:EntityDescriptor
  xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
  xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
  entityID="https://sso.partner.example/issuer">
  <md:IDPSSODescriptor
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <!-- KeyDescriptor use=signing #1 mang C_old theo chuẩn X.509 -->
    <!-- KeyDescriptor use=signing #2 mang C_new theo chuẩn X.509 -->
    <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://sso.partner.example/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

**Đoạn trên không phải metadata có thể import** vì cố ý lược nội dung X.509 certificate thật, các thuộc tính và chữ ký metadata có thể bắt buộc. Hãy lấy metadata **thực tế do IdP phát và đã xác minh**. Nếu metadata có `KeyDescriptor` mà không có `use`, SAML metadata có thể diễn giải khóa đó dùng cho nhiều mục đích theo profile; cần đọc đúng semantics thay vì tự đoán “khóa đầu là signing”.

**Một XML file có hai chứng thư không chứng minh hai chứng thư thuộc IdP đúng.** Cần xác thực nguồn phân phối, chính sách ký metadata/trust anchor, issuer dự kiến và change approval. Không sử dụng chứng thư được nhúng trực tiếp trong SAMLResponse hoặc URL do browser truyền tới để tự cập nhật trust set.

### 5.2. Certificate fingerprint, issuer, validity và key usage

Khi nhận C_new, đội tích hợp cần ghi ít nhất:

- SHA-256 fingerprint của **certificate DER** (không dùng SHA-1 làm tiêu chuẩn duy nhất).
- Subject, issuer DN, serial number, `NotBefore`, `NotAfter` và thuật toán/chỉ số khóa.
- Nguồn nhận certificate, thời điểm và người phê duyệt, bên sở hữu IdP.
- Công dụng: SAML signing verification; không tự chuyển thành TLS server trust hoặc SP decryption credential.
- Kế hoạch bắt đầu sử dụng và chấm dứt chấp nhận, phiên bản cấu hình/metadata.
- Bằng chứng từ kênh độc lập khi có thay đổi signing key: ticket được duyệt, metadata có chữ ký từ trust anchor đã biết hoặc kênh IdP operator đã xác thực.

Lệnh kiểm tra public certificate:

```bash
keytool -printcert -file idp-signing-old.crt
keytool -printcert -file idp-signing-next.crt
```

`keytool` đi cùng JDK; đầu ra phụ thuộc certificate thật và phiên bản JDK nên bài không gán stdout cố định. Lệnh này **chỉ kiểm tra cấu trúc/fingerprint thông tin**; nó không xác minh certificate mới đã được **IdP có thẩm quyền phê duyệt**. Để kiểm tra hai bản certificate có cùng key hay không, có thể so sánh public-key fingerprint/SPKI phù hợp; **hai certificate có serial/fingerprint khác chưa chắc đã là hai private keys khác nhau** nếu IdP tái dùng key. Việc luân chuyển hiệu quả nên xem xét tạo **key pair mới** khi chính sách yêu cầu.

### 5.3. X.509 hết hạn và tính hợp lệ chữ ký SAML là hai câu chuyện

Việc xác minh chữ ký XML bằng public key không tự đồng nghĩa bộ thư viện đã thực hiện **mọi** kiểm tra PKIX/path validation và thời hạn certificate như một TLS browser. Một số triển khai SAML sử dụng certificate như khóa công khai được pin trong metadata, không xác minh chain X.509 theo cùng mô hình TLS. Vì vậy:

- Xem rõ Spring Security/OpenSAML và chính sách của tổ chức xử lý `NotBefore/NotAfter` của certificate ra sao; nếu yêu cầu chặn cert hết hạn, phải **thực thi và kiểm thử** chính sách ấy.
- Không suy từ “SAMLResponse ký đúng” ra “certificate chưa hết hạn”, hoặc suy từ “certificate TLS valid” ra “SAML assertion signing valid”.
- Lịch luân chuyển phải có **mốc trước certificate expiry**, không chờ đến ngày cuối mới phát C_new.
- Một khóa trong trust set phải có trạng thái `ACTIVE/OVERLAP/RETIRED/REVOKED` do policy quản lý; không dựa duy nhất vào thứ tự certificate trong metadata.

## 6. Cấu hình Spring Boot: chấp nhận C_old và C_new ở cùng IdP

### 6.1. Cấu hình bằng application.yml

Giả định Spring Boot/Spring Security servlet stack tương thích với Java 17+, dependency `spring-security-saml2-service-provider`, IdP hợp lệ và hai **file public certificate thật** đã được phê duyệt nằm trong `src/main/resources/saml/`.

File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/partner"
            assertion-consumer-service-location: "https://app.example.org/login/saml2/sso/partner"
            assertingparty:
              entity-id: "https://sso.partner.example/issuer"
              singlesignon:
                url: "https://sso.partner.example/saml/sso"
                binding: REDIRECT
                sign-request: false
              verification:
                credentials:
                  - certificate-location: classpath:saml/idp-signing-old.crt
                  - certificate-location: classpath:saml/idp-signing-next.crt
```

**Ý nghĩa cấu hình:**

- Hai phần tử `verification.credentials` được dùng để SP **xác minh chữ ký từ cùng asserting party**. Đây là hai **public certificates** riêng biệt, không phải private keys.
- `registration.partner` xác định đúng quan hệ IdP–SP. Với nhiều IdP, mỗi registration phải có **tập verify credentials của chính IdP đó**; không gom tất cả chứng thư từ mọi issuer vào một danh sách chung.
- `entity-id` của SP là giá trị IdP nên dùng trong `AudienceRestriction`. `assertion-consumer-service-location` là URL nên dùng ở `Recipient`/`Destination`. Thêm khóa mới **không thay đổi** các giá trị này.
- `assertingparty.entity-id` là định danh IdP; phải trùng nguồn đã phê duyệt. Đừng mở thêm issuer hoặc nới audience để “bù” cho việc đổi signing certificate.
- `singlesignon.url` là endpoint IdP nhận AuthnRequest, không phải nơi SP nhận SAMLResponse. `sign-request: false` chỉ là ví dụ IdP test cho phép unsigned AuthnRequest; nếu IdP yêu cầu ký request thì cần **SP signing credentials** riêng.
- Dùng classpath cho nội dung minh họa: thay certificate trong artifact sẽ cần redeploy/restart nếu ứng dụng không có cơ chế reload thích hợp. **Không coi sửa file trên disk là đủ để Spring tự nạp lại bean immutable.**
- Không bao giờ đặt private key IdP vào classpath/SP repository.

**Thay đổi theo giai đoạn:** Phase 0 chỉ có dòng `idp-signing-old.crt`; Phase 1–2 giữ cả hai dòng; Phase 3 chỉ còn dòng `idp-signing-next.crt`. Mỗi thay đổi phải được triển khai toàn bộ node, có kiểm thử và không tạo ra thời gian ngắn mà SP không tin khóa IdP đang dùng.

Các domain ở đây là **ví dụ**, không phải endpoint thật có thể dùng ngay. Khi chạy với IdP test, phải dùng certificate được IdP cung cấp từ nguồn đã xác minh và cập nhật entityID/ACS/SSO URL thực tế.

### 6.2. Nếu IdP metadata đang là nguồn cấu hình

Spring Security có thể dựng `RelyingPartyRegistration` bằng `RelyingPartyRegistrations.fromMetadataLocation("https://...")`. Nếu IdP metadata được quản lý đúng, khi công bố hai certificate signing, parser có thể đưa chúng vào tập verification credentials.

Nhưng cần phân biệt:

1. **Nạp metadata lúc khởi động** không đồng nghĩa có cơ chế tự refresh sau khi IdP đổi XML.
2. **Metadata HTTP có chứng thư TLS hợp lệ** không tự động cho phép mỗi key mới trong XML trở thành trust mà không kiểm tra nguồn/chính sách.
3. **Metadata XML có phần tử Signature** không bảo đảm Spring đã kiểm tra signature nếu bạn chưa cấu hình verification credentials/trust anchor cho chính metadata.
4. **Một repository có cache/refresh** phải được kiểm tra thực tế về TTL, reload, outage fallback, signature validation và atomic update.
5. **URI metadata** không được lấy trực tiếp từ browser/tenant để backend tải; kiểm soát URL, redirect/SSRF và mạng egress.

Tài liệu Spring Security cung cấp `AssertingPartyMetadataRepository` và các triển khai `OpenSaml5AssertingPartyMetadataRepository` dựa trên metadata resolver để refresh theo expiry. Tài liệu cũng nêu rằng khi dùng API verify metadata signature mà **không cung cấp verification credentials**, chữ ký metadata có thể **không được kiểm tra**. Vì vậy `fromTrustedMetadataLocation`/URL tin cậy không phải phép màu bảo đảm xác minh mọi chữ ký XML theo chính sách bạn mong muốn.

**Chính sách khuyến nghị:** Dùng metadata được ký và trust anchor quản trị độc lập khi federation yêu cầu; cố định issuer, nguồn URL/egress; kiểm tra diff và tổ chức change approval khi có signing key mới. Kết quả metadata refresh phải được ánh xạ tới **registration đúng tenant**, không cập nhật khóa từ IdP A vào IdP B.

## 7. Ví dụ Java 17+/Spring Security: hai verification credentials

Với một ứng dụng Spring Boot Java 17+ có các dependency `spring-boot-starter-web`, `spring-boot-starter-security` và `spring-security-saml2-service-provider`, bạn có thể tạo `RelyingPartyRegistrationRepository` tường minh.

File `src/main/java/com/example/federation/SamlTrustConfig.java`:

```java
package com.example.federation;

import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlTrustConfig {

    static X509Certificate certificate(String resource) throws Exception {
        try (InputStream in =
                 new ClassPathResource(resource).getInputStream()) {
            return (X509Certificate)
                CertificateFactory.getInstance("X.509")
                    .generateCertificate(in);
        }
    }

    @Bean
    RelyingPartyRegistrationRepository registrations() throws Exception {
        X509Certificate oldCert =
            certificate("saml/idp-signing-old.crt");
        X509Certificate newCert =
            certificate("saml/idp-signing-next.crt");

        // Cả hai certificate phải được phê duyệt cho CÙNG IdP.
        Saml2X509Credential oldVerification =
            Saml2X509Credential.verification(oldCert);
        Saml2X509Credential newVerification =
            Saml2X509Credential.verification(newCert);

        RelyingPartyRegistration partner =
            RelyingPartyRegistration.withRegistrationId("partner")
                .entityId(
                    "https://app.example.org/saml2/service-provider-metadata/partner")
                .assertionConsumerServiceLocation(
                    "https://app.example.org/login/saml2/sso/partner")
                .assertingPartyMetadata(idp -> idp
                    .entityId("https://sso.partner.example/issuer")
                    .singleSignOnServiceLocation(
                        "https://sso.partner.example/saml/sso")
                    .verificationX509Credentials(credentials -> {
                        credentials.add(oldVerification);
                        credentials.add(newVerification);
                    }))
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(partner);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
```

**Cách hiểu:**

- `Saml2X509Credential.verification(...)` tạo credential **để xác minh**; không tạo key ký AuthnRequest.
- `verificationX509Credentials(...)` nhận một collection; thêm cả `oldVerification` và `newVerification` vào registration của đúng IdP. Chính Spring Security/OpenSAML sẽ sử dụng tập credential trong xác thực message theo implementation/version.
- Bộ lọc `saml2Login` và ACS mặc định tiếp tục hoạt động; việc đổi tập certificate **không yêu cầu viết controller tự parse Base64 XML**.
- Đoạn này đọc các file **khi xây bean**; trong giai đoạn retire phải thay bean/redeploy theo quy trình. Không chỉ xóa file `idp-signing-old.crt` trên disk trong khi bean còn giữ chứng thư ở bộ nhớ.
- Cần file certificate thật và IdP test đã phê duyệt; đây là **mã tích hợp trong project Spring**, không phải chương trình độc lập biên dịch bằng `javac` khi không có Spring dependencies.
- Nếu cần `AuthnRequest` ký theo yêu cầu IdP, bổ sung **SP signing credential** và cấu hình protocol phù hợp, **không** lấy một trong hai verify credentials của IdP để ký.
- `SecurityFilterChain` ở đây minh họa cách bật SAML; ứng dụng thực phải công khai các endpoint login/AuthnRequest/ACS/metadata cần thiết và bảo vệ tài nguyên nghiệp vụ theo chính sách. Spring SAML filters chạy trước khi chỉ định Authentication; **không bỏ** chữ ký/issuer/audience validation.
- Khi dùng nhiều Spring Security major versions, API builder/provider có thể thay đổi; đối chiếu Spring Security reference/API của đúng phiên bản và chạy integration tests trước khi triển khai.

### 7.1. Mã Spring trên không làm những gì?

Nó **không**:

- Tự kiểm tra SHA-256 fingerprint mới đối chiếu với ticket/change management.
- Tự tải hoặc verify metadata signature, refresh cache, xử lý rollback/retirement date.
- Áp policy riêng cho X.509 expiry, key strength/algorithm, issuer DN nếu tổ chức yêu cầu.
- Đảm bảo mọi pod/region đều có bản cập nhật trong cùng thời điểm.
- Làm mất hiệu lực những session SAML đã tạo từ trước khi certificate bị thu hồi.
- Phân biệt luồng IdP-initiated không có `InResponseTo`; SP phải quyết định riêng.

Các phần này thuộc **vận hành, governance và bổ sung security policy**. Một danh sách hai chứng thư chỉ là **cơ chế kỹ thuật** cho overlap, không thay thế kế hoạch đổi khóa.

## 8. Java 17 chạy độc lập: nguyên lý chấp nhận hai public keys

Để hiểu chính xác khái niệm “cả khóa cũ và mới cùng verify được”, ví dụ sau dùng RSA/SHA-256 từ JDK 17. Chương trình sinh hai key pairs **giả lập**, ký cùng một chuỗi test bằng từng private key, rồi xác minh bằng tập public keys theo từng phase.

**Đây chỉ là minh họa chữ ký mật mã**, **không tạo SAMLResponse, không parse XML Signature/canonicalization, không có certificate thật và không phải SAML validator**. Không dùng class này thay OpenSAML.

File `DualKeyVerificationDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.List;

public class DualKeyVerificationDemo {

    static byte[] sign(byte[] data, PrivateKey privateKey)
            throws Exception {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(privateKey);
        signer.update(data);
        return signer.sign();
    }

    static boolean verifyWithAnyTrustedKey(
            byte[] data, byte[] signature, List<PublicKey> trusted)
            throws Exception {
        for (PublicKey key : trusted) {
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(key);
            verifier.update(data);
            if (verifier.verify(signature)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair oldKey = generator.generateKeyPair();
        KeyPair newKey = generator.generateKeyPair();
        KeyPair unknownKey = generator.generateKeyPair();

        byte[] message =
            "trusted-saml-fixture".getBytes(StandardCharsets.UTF_8);
        byte[] altered =
            "tampered-saml-fixture".getBytes(StandardCharsets.UTF_8);

        byte[] signedOld = sign(message, oldKey.getPrivate());
        byte[] signedNew = sign(message, newKey.getPrivate());
        byte[] signedUnknown = sign(message, unknownKey.getPrivate());

        List<PublicKey> oldOnly = List.of(oldKey.getPublic());
        List<PublicKey> overlap = List.of(
            oldKey.getPublic(), newKey.getPublic());
        List<PublicKey> newOnly = List.of(newKey.getPublic());

        System.out.println("oldBefore=" +
            verifyWithAnyTrustedKey(message, signedOld, oldOnly));
        System.out.println("newBefore=" +
            verifyWithAnyTrustedKey(message, signedNew, oldOnly));
        System.out.println("oldDuring=" +
            verifyWithAnyTrustedKey(message, signedOld, overlap));
        System.out.println("newDuring=" +
            verifyWithAnyTrustedKey(message, signedNew, overlap));
        System.out.println("unknownDuring=" +
            verifyWithAnyTrustedKey(message, signedUnknown, overlap));
        System.out.println("tamperedDuring=" +
            verifyWithAnyTrustedKey(altered, signedNew, overlap));
        System.out.println("oldAfter=" +
            verifyWithAnyTrustedKey(message, signedOld, newOnly));
        System.out.println("newAfter=" +
            verifyWithAnyTrustedKey(message, signedNew, newOnly));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac --release 17 DualKeyVerificationDemo.java
java DualKeyVerificationDemo
```

Stdout chính xác (dù RSA sinh khóa ngẫu nhiên, kết quả boolean ổn định):

```text
oldBefore=true
newBefore=false
oldDuring=true
newDuring=true
unknownDuring=false
tamperedDuring=false
oldAfter=false
newAfter=true
```

Kết quả minh họa vòng đời:

- `oldBefore=true`: trạng thái ban đầu tin K_old.
- `newBefore=false`: IdP đổi sang ký K_new quá sớm sẽ lỗi.
- `oldDuring=true` và `newDuring=true`: khoảng overlap thật sự.
- `unknownDuring=false`: **dual trust không có nghĩa trust all**.
- `tamperedDuring=false`: message bị đổi sau ký không hợp lệ.
- `oldAfter=false` và `newAfter=true`: loại K_old sau cửa sổ luân chuyển.

**Không dùng dấu hiệu “signature valid” làm toàn bộ quyết định đăng nhập:** XML SAML còn phải qua issuer/audience/recipient/time/InResponseTo/replay và cấu trúc được ký. Chương trình demo không mô phỏng các validator đó.

## 9. Phương án refresh IdP metadata: đồng bộ khóa mới có kiểm soát

Khi IdP metadata là **nguồn sự thật**, hệ thống SP có thể cập nhật khóa từ XML đã được phê duyệt thay vì đóng gói từng certificate vào binary. Đây là cơ chế tốt cho federation có nhiều đối tác, nhưng không tự bảo đảm toàn bộ security controls.

### 9.1. Mô hình tải/refresh

```text
Job theo lịch / metadata resolver
       |
       | GET HTTPS metadata URI cố định của đúng IdP
       v
[Giới hạn URL, redirect, DNS/egress, timeout, kích thước]
       |
       v
[Parse XML an toàn + kiểm chứng issuer/metadata signature]
       |
       v
[So sánh fingerprint C_old, C_new với chính sách/approval]
       |
       v
[Đối chiếu KeyDescriptor use=signing, SSO endpoint, validUntil]
       |
       v
[Staged trust set: {C_old,C_new}]
       |
       v
[Atomic publish/refresh RelyingPartyRegistrationRepository]
       |
       v
[Smoke test và giám sát từng tenant/region]
```

**Quan trọng về metadata signature:** Chữ ký của chính SAML metadata phải được xác minh bằng **trust anchor độc lập** nếu dùng mô hình signed metadata. Không được lấy certificate mới từ **metadata chưa xác minh** làm khóa xác minh lại chính metadata đó; điều này có thể cho phép kẻ tấn công tự ký file giả. Nếu không dùng signed metadata, phải có cơ chế xác thực nguồn, phê duyệt và kiểm soát thay đổi tương đương theo policy.

### 9.2. API Spring Security liên quan

- `RelyingPartyRegistrations.fromMetadataLocation(...)`: khởi dựng từ metadata location; hữu ích nhưng **không mặc định là refresh theo lịch và kiểm soát rủi ro rollover**.
- `AssertingPartyMetadataRepository`: abstractions để quản lý asserting party metadata tách khỏi SP registration.
- `OpenSaml5AssertingPartyMetadataRepository`: có thể dùng OpenSAML MetadataResolver để refresh theo hạn hiệu lực; đối chiếu chính xác version và builder.
- `CachingRelyingPartyRegistrationRepository`: có thể dùng cache cho registration nhưng cần nắm TTL/cache invalidation khi metadata thay đổi.
- `RelyingPartyRegistrationRepository`: mỗi login phải lấy đúng registration chứa **tập khóa hiệu lực**; tránh repository cache cũ trên một số node.
- `saml2Metadata(...)`: công bố metadata **của SP**, không phải tự động cập nhật IdP signing certificate.

Tài liệu Spring Security cho thấy có thể cấu hình verification credentials cho metadata signature, đồng thời cảnh báo nếu **không** cung cấp credentials thì API tương ứng có thể không thực hiện signature validation. Đội vận hành phải xác minh hành vi thật bằng integration test, không suy đoán từ tên API “trusted”.

### 9.3. Không chấp nhận mọi thay đổi metadata cùng lúc

Thay `KeyDescriptor use="signing"` là một thay đổi đúng mục tiêu rollover. Nhưng nếu cùng bản metadata đột ngột thay:

- `entityID` của IdP,
- SingleSignOnService Location sang domain mới,
- SingleLogoutService endpoints,
- danh sách các KeyDescriptor khác loại,
- metadata signature trust anchor,
- tenant/registration mapping,

thì phải **đánh giá riêng**. Không “approve all diff” chỉ vì đang đổi cert. Một metadata refresh hợp lệ không có nghĩa issuer mới và SSO endpoint mới được tự động tin. Đây là biện pháp ngăn lợi dụng đợt rotation làm thay đổi ranh giới federation.

### 9.4. Khi refresh thất bại

Nếu URL metadata timeout, trả 30x lạ, XML sai chữ ký hoặc file quá hạn:

1. Không tự đi theo URL redirect chưa phê duyệt hoặc bật TLS trust-all.
2. Giữ trạng thái trust gần nhất **chỉ khi** policy cho phép dùng bản đã phê duyệt và còn hiệu lực; nếu không, fail closed.
3. Alert đúng partner, lỗi và node, không ghi raw SAMLResponse/secret.
4. Không tự bỏ C_old hoặc chấp nhận C_new chưa xác minh để “sửa” login.
5. Khôi phục qua bản metadata trước đã được phê duyệt hoặc tiếp tục chờ phiên bản metadata đúng; xem xét giới hạn thời gian cache và rollback.

## 10. Kiểm thử giai đoạn overlap: phải phát được cả chữ ký cũ và mới

### 10.1. Kiểm thử ở lớp nào?

Một phép test `Signature.verify()` với hai public keys chỉ kiểm tra mật mã. Cần **integration test SAML thật** với IdP test phát SAMLResponse/Assertion đã ký bằng private keys tương ứng, trong khi issuer, audience, recipient, request correlation và thời gian được giữ hợp lệ.

Thực hiện trong sandbox:

1. Tạo hai key pairs thử nghiệm riêng ở IdP test, đưa public certificates qua kênh tin cậy.
2. Cấu hình SP chỉ tin cert cũ, thực hiện đăng nhập SP-initiated bằng khóa cũ.
3. Thêm cert mới vào SP trước khi IdP chuyển; xác nhận **both old and new accepted** ở mọi node.
4. Chuyển IdP test ký bằng khóa mới; xác nhận SSO thành công.
5. Loại cert cũ khỏi SP test; xác nhận message ký bằng cũ bị từ chối.
6. Ký bằng khóa không thuộc IdP; xác nhận SP không chấp nhận ngay cả khi `Issuer`/`Audience` trông đúng.
7. Kiểm tra chữ ký hợp lệ nhưng `Audience`/`Recipient`/`InResponseTo` sai vẫn bị từ chối.
8. Nếu có SAML Single Logout, kiểm tra cả LogoutRequest/LogoutResponse ký bằng key được IdP dùng, không chỉ login.

**Không sửa raw XML đã ký để kiểm thử audience rồi kết luận từ lỗi signature.** Hãy thay claim tại IdP test hoặc fixture builder rồi ký lại với private key thử nghiệm; nếu không sẽ chỉ chứng minh checksum/chữ ký hỏng.

### 10.2. Ma trận trạng thái bắt buộc

| Phase | Khóa ký message | SP trust set | Kết quả với assertion còn hợp lệ |
| --- | --- | --- | --- |
| Trước overlap | K_old | `{C_old}` | **Chấp nhận** |
| Trước overlap | K_new | `{C_old}` | **Từ chối** |
| Trong overlap | K_old | `{C_old,C_new}` | **Chấp nhận** |
| Trong overlap | K_new | `{C_old,C_new}` | **Chấp nhận** |
| Trong overlap | K_unknown | `{C_old,C_new}` | **Từ chối** |
| Trong overlap | K_old nhưng issuer SP khác | `{C_old,C_new}` | **Từ chối** vì issuer/registration |
| Trong overlap | K_new nhưng audience SP khác | `{C_old,C_new}` | **Từ chối** vì audience |
| Trong overlap | K_new nhưng recipient/ACS sai | `{C_old,C_new}` | **Từ chối** vì destination/subject confirmation |
| Trong overlap | K_new với assertion hết hạn | `{C_old,C_new}` | **Từ chối** vì thời gian |
| Trong overlap | K_new với InResponseTo sai | `{C_old,C_new}` | **Từ chối** theo correlation |
| Sau retire | K_old | `{C_new}` | **Từ chối**, kể cả chữ ký cũ từng hợp lệ |
| Sau retire | K_new | `{C_new}` | **Chấp nhận** |
| Bất kỳ phase | K_new ký metadata tự tạo nhưng metadata trust anchor sai | Metadata validation | **Không cập nhật** trust set |
| Bất kỳ phase | Chứng thư mới từ tenant khác | Trust set IdP A | **Không chấp nhận** |
| Bất kỳ phase | SAMLResponse không ký hoặc sai signature | Bất kỳ | **Từ chối** |

Kết quả “chấp nhận” chỉ đúng nếu **mọi kiểm tra SAML khác** đạt và ứng dụng có chính sách cho phép user/claim. Đừng so sánh mỗi HTTP status 302/200: sau lỗi login cũng có thể redirect về login page. Bằng chứng cần là **Authentication/session được tạo đúng** hoặc thất bại xác thực đúng như dự kiến.

### 10.3. Kiểm tra trên nhiều node/region/tenant

Một SP có nhiều pod có thể có trust set khác nhau do rolling deployment hoặc cache. Test cần đảm bảo:

- Mỗi node đã nạp C_new trước thời điểm IdP switch.
- Không tồn tại một vùng/tenant bị bỏ sót cập nhật.
- Blue/green deployment và rollback image không tự kéo trust set về `{C_old}` sau T1.
- ConfigMap/secret/classpath/repository cache đã refresh thực sự; kiểm tra trạng thái hiệu lực chứ không chỉ file mới xuất hiện trên disk.
- Các job background có thể xử lý SAML logout hoặc message SAML khác đều nhận đủ certificate.
- Rollover được triển khai độc lập cho từng IdP/tenant; không có việc thay trust set của IdP A kéo theo IdP B.

Nếu team dùng canary, chỉ tăng tỷ lệ traffic sau khi test cả hai khóa. Trước khi IdP ký mới, **tất cả node thực sự nhận login** phải sẵn sàng, không chỉ 1% canary.

## 11. Logging và metric đủ để kết luận “đã sẵn sàng”

Ghi nhận những trường có giá trị vận hành:

```text
timestamp_utc
registration_id
verified_idp_entity_id
trust_set_version
approved_certificate_fingerprint_sha256
signature_verification_result
failure_category
deployment_version
node_or_region
authentication_result
metadata_refresh_age
```

**Không log** private key, raw SAMLResponse/SAMLAssertion, NameID/email nhạy cảm, session cookie hoặc cả tài liệu metadata nếu nó chứa thông tin không nên công khai. Fingerprint **công khai** của certificate hữu ích để biết request đã được xác minh bằng khóa nào, nhưng việc ghi “key used” phải dựa trên provider đã xác minh thật, **không chỉ đọc KeyInfo do request tự khai**.

Một số Spring/OpenSAML API không cung cấp trực tiếp “certificate đã được chọn” ở event authentication mặc định; khi đó phải instrument ở lớp provider/metadata/trust service phù hợp, hoặc dùng smoke tests và trust-set version từ config. **Không tự suy certificate đã được dùng chỉ từ fingerprint do người gửi chèn trong XML chưa được tin**.

Các metric cơ bản:

- Số lượng/tỷ lệ SAML logins **thành công** theo registration/region.
- Signature/trust failures theo IdP và key rotation window.
- Lần refresh metadata thành công gần nhất, TTL, số node có trust-set version mới.
- Hạn hiệu lực của certificate cũ/mới và số ngày còn lại tới retirement deadline.
- Số request SAML hợp lệ từ old key sau cutover, nếu đo được bằng công cụ đáng tin.
- Ngày/giờ hoàn thành loại C_old ở tất cả SP và bằng chứng rằng signed-old đã bị từ chối.
- Cảnh báo cao nếu xuất hiện unknown certificate hoặc metadata issuer/SSO endpoint đổi không theo kế hoạch.

## 12. Khác biệt quan trọng: đổi khóa định kỳ và xử lý lộ khóa

### 12.1. Rotation có kế hoạch

Được phép có overlap theo deadline, vì K_old **chưa bị coi là lộ**. Mục tiêu là bảo toàn tính sẵn sàng trong khi đảm bảo trust set chỉ bao gồm hai khóa đã kiểm tra. Khi kết thúc phải thu hồi K_old.

### 12.2. Nghi lộ IdP private signing key cũ

Đây **không phải** tình huống nên giữ cả hai khóa để tránh downtime. Nếu K_old bị nghi lộ, một kẻ có private key có thể ký các assertion giả mạo. Cần ưu tiên **containment**:

1. Kích hoạt incident response, xác minh phạm vi/hệ IdP, thông báo tất cả SP owner.
2. **Loại C_old khỏi trust set của SP càng sớm càng phù hợp với mức độ sự cố**, kể cả khi điều đó tạm làm gián đoạn SSO; không dùng overlap vô thời hạn với khóa đã xâm phạm.
3. IdP ngừng dùng/revoke K_old, đưa K_new đã được xác minh vào hoạt động; SP xác nhận không còn tin C_old ở tất cả node/cache.
4. Kiểm tra khả năng IdP/metadata signing trust cũng bị ảnh hưởng; nếu trust anchor phân phối metadata bị lộ, phải thay/đánh giá qua kênh độc lập thay vì tin metadata hiện tại.
5. Rà soát sessions đã tạo bằng assertions có thể bị giả mạo, cân nhắc revoke/force re-authenticate theo phạm vi sự cố, log bằng chứng mà không lộ PII.
6. Kiểm tra xâm nhập của IdP, lưu evidence phù hợp, tránh tự xác định “chỉ bị lộ K_old” khi chưa có bằng chứng.
7. Khôi phục dịch vụ sau khi trust chain mới và tất cả SAML checks được xác nhận.

**Độ ưu tiên:** Trong một compromise, **tính toàn vẹn xác thực quan trọng hơn tránh mọi gián đoạn**. Không bật “skip signature validation”, “accept any certificate” hoặc “trust XML-embedded cert” để giảm lỗi đăng nhập.

### 12.3. Certificate gần hết hạn nhưng chưa lộ khóa

Hạn certificate gần hết là tín hiệu lập lịch rotation, không mặc nhiên là compromise. Khi một ứng dụng chưa sẵn sàng nhận C_new và C_old sắp hết hạn, có thể cần **thời gian bảo trì có kế hoạch** thay vì phá policy. Đừng sửa thời gian hệ thống hoặc nới vô hạn certificate-validity checks để tiếp tục dùng khóa cũ.

## 13. Những lỗi phổ biến khi rollover

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Chỉ một số người dùng login lỗi sau cutover | SP pod/region/tenant khác nhau vẫn dùng trust set cũ | Kiểm tra trust-set version từng node, rollout/cache/rollback |
| IdP đổi cert; SP báo signature invalid | C_new chưa có trong `verification.credentials`, cert không đúng, assertion được ký bằng khóa khác | So khớp fingerprint được IdP xác nhận; kiểm tra đúng IdP/registration và certificate thật |
| Spring dùng cert mới nhưng vẫn bị reject | Issuer, audience, recipient, destination, time, replay hoặc thuật toán chữ ký không đạt | Chẩn đoán từng validator; không tự kết luận là cert |
| Metadata có hai cert nhưng SP chỉ dùng một | Parser/config chỉ lấy first KeyDescriptor, cache/repository không refresh, code tự ghi đè collection | Kiểm tra registration hiệu lực, metadata parser và tập verification credentials |
| C_new được đưa vào nhưng SAML login vẫn lỗi trước switch | SP signing key bị nhầm với IdP verification key, hoặc cấu hình YAML sai cấp | Tách signing/decryption của SP khỏi verification của IdP |
| Certificate mới khác fingerprint trong ticket | Sai phiên bản metadata, giả mạo hoặc nhầm tenant | Dừng nạp khóa, kiểm chứng out-of-band và yêu cầu approval |
| XML metadata tải qua HTTPS nhưng trust bị thay lạ | Metadata signature/trust anchor chưa kiểm, nguồn bị xâm nhập hoặc bị redirect | Quản lý trusted URL/metadata signature/egress, review diff |
| Certificate old đã bị bỏ nhưng vẫn xác minh được | Một node/cache giữ C_old; rollback đưa lại cert; test đi sai SP | Test signed-old ở từng node, kiểm tra cache và version |
| IdP đã chuyển ký mới nhưng logout SAML thất bại | SLO messages còn dùng khóa cũ hoặc xử lý khác | Bao gồm SLO trong test matrix và lịch decommission |
| Lỗi “certificate expired” | Validity policy chặn một cert, NTP drift, rollover quá muộn | Kiểm tra mốc X.509, thời gian UTC và lịch chuyển khóa |
| Login thành công nhưng quyền sai | Nhóm/attribute mapping hoặc application authorization lỗi, độc lập với certificate | Kiểm tra quyền theo issuer/tenant đã xác minh |
| Đổi K_new nhưng lại dùng thuật toán không hỗ trợ | Thuật toán chữ ký/KeyInfo/provider policy không tương thích | Thống nhất RSA/ECDSA, digest/signing algorithm và profile trước cutover |
| Trust set chứa cert giống nhau hai lần | Duplicate metadata/merge cấu hình không sạch | Dedupe theo public cert fingerprint nhưng vẫn giữ audit đúng nguồn |
| Certificate cũ vẫn còn trong artifact/source control | Decommission chưa hoàn tất hoặc build cache | Loại khỏi config/classpath/repository, rebuild/redeploy và kiểm tra trust hiệu lực |

**Sơ đồ chẩn đoán:**

```text
Có đúng SAMLResponse tới HTTPS ACS?
    |
    v
Đúng registration + IdP entityID?
    |
    v
SP có đúng C_old/C_new đã phê duyệt trong trust set?
    |
    v
Chữ ký trên message/assertion đúng khóa, thuật toán và XML?
    |
    v
Audience / Recipient / Destination / InResponseTo / time đều đạt?
    |
    v
Ứng dụng tạo Authentication/session?
    |
    v
Permission/tenant/role có đúng?
```

Thứ tự này giúp không nhầm **lỗi tích hợp khóa** với **lỗi user/authorization** hoặc **lỗi reverse proxy**.

## 14. Vận hành nhiều IdP và nhiều giao thức trong một hệ thống

Spring Security có thể vừa nhận SAML từ nhiều IdP vừa nhận OIDC từ OP khác. Mỗi loại có cách phát hiện khóa:

- **SAML IdP:** public X.509 signing certificate được cấu hình trong metadata/registration; có thể chứa **hai `KeyDescriptor use="signing"`** trong overlap.
- **OIDC/JWT:** OP công bố `jwks_uri` với nhiều JWKs; verifier thường chọn key theo `kid`/alg/trust issuer, vẫn phải kiểm tra `iss`/`aud`/`exp`. Không lấy logic `kid` của JWT áp thẳng vào XML Signature SAML.
- **CAS:** service validation tin server/certificate/transport riêng, không mặc nhiên có cơ chế X.509 assertion signing như SAML.

Với SAML, `<ds:KeyInfo>` trong message có thể chứa thông tin chứng thư/định danh khóa, nhưng đó là dữ liệu **của message được nhận**. Nó có thể là hint cho quá trình tìm khóa, **không thay thế** tập public keys đã được trust cho issuer.

Nếu ứng dụng là identity broker, phải luân chuyển khóa **đầu vào** (verify IdP assertions) và khóa **đầu ra** (broker ký token/asertion cho downstream RP) theo hai kế hoạch riêng. Không tạo một trust set toàn cục cho mọi đối tác.

## 15. Bài thực hành có thể lặp lại

### 15.1. Chuẩn bị

1. Tạo IdP SAML test với hai key pairs riêng, public certificate `C_old`/`C_new`.
2. Tạo SP Spring Boot test có cùng `entityID`, `ACS` và IdP issuer được cấu hình ổn định.
3. Đăng ký SP ở IdP, bật ký Response/Assertion phù hợp yêu cầu.
4. Ghi fingerprint SHA-256 của hai certificate qua `keytool -printcert`.
5. Tạo bộ dữ liệu user test, browser session độc lập và log ở mức không lộ SAML assertion.
6. Định nghĩa ngưỡng QA: mọi signed-old/signed-new test đúng theo phase, unknown key luôn từ chối, audience/recipient/correlation vẫn hoạt động.

### 15.2. Thực hiện

**Phase 0:** SP chỉ tin C_old. Login ký old thành công, ký new bị từ chối.

**Phase 1:** SP tin cả C_old+C_new. Test signed-old/signed-new ở mọi node; người dùng không phải đổi account và SP không chấp nhận issuer khác.

**Phase 2:** IdP ký bằng K_new. Test browser full SSO, signed old in-flight trong phạm vi cho phép, không làm lỗi session và SLO. Theo dõi ít nhất suốt cửa sổ đổi khóa đã phê duyệt.

**Phase 3:** SP chỉ tin C_new. Test signed-new thành công và signed-old thất bại. Rà soát repository/classpath/cache/container image không còn C_old ở danh sách trusted; metadata cuối cùng chỉ công bố C_new.

### 15.3. Đầu ra cần bàn giao

Một biên bản có đủ:

| Mục | Bằng chứng |
| --- | --- |
| IdP entityID, SP entityID/ACS | Values trong metadata đã xác minh |
| SHA-256 fingerprints | `C_old` và `C_new` từ nguồn có thẩm quyền |
| Timeline | Ngày phát hành, prepublish, SP dual trust, IdP switch, retirement |
| Danh sách SP/nodes | Trạng thái trust-set version trước/sau |
| Test signed-old và signed-new | Pass/fail theo từng phase, kèm method/binding |
| Unknown/unauthorized cert negative test | Bị từ chối, không tạo session |
| SAML validation negative tests | Audience/recipient/issuer/time/replay bị từ chối |
| Monitoring | Không có spike xác thực thất bại sau cutover |
| Metadata refresh/trust anchor | Xác nhận nguồn và chữ ký metadata nếu áp dụng |
| Incident/rollback policy | Điều kiện rollback, stop-go và owner |
| Retirement evidence | C_old không còn trong active trust set ở mọi node |

## 16. Checklist production và điều kiện hoàn thành

- [ ] Xác minh chính xác IdP/registration/tenant của từng certificate, không nhập cert từ message chưa tin.
- [ ] Hai certificate `C_old` và `C_new` đều là **public signing certificates** của IdP, fingerprint được duyệt độc lập.
- [ ] IdP prepublish C_new khi vẫn ký K_old, tránh đổi khóa trước khi SP sẵn sàng.
- [ ] SP chấp nhận đồng thời C_old+C_new chỉ trong cửa sổ có **deadline**; không mở rộng issuer/ACS/permissions.
- [ ] Toàn bộ pod/region/tenant/cluster có trust-set version mới trước khi IdP cutover.
- [ ] Test SAMLResponse ký old và new đầy đủ, không chỉ kiểm tra file XML/YAML.
- [ ] Chữ ký từ unknown key bị từ chối; audience/recipient/issuer/time/InResponseTo vẫn được kiểm tra.
- [ ] Metadata refresh có trusted source, giới hạn URL/SSRF, chữ ký/trust anchor phù hợp và audit diff.
- [ ] Kiểm soát certificate validity, thuật toán, key size và đồng hồ theo chính sách, không coi verify XML là check PKIX hoàn chỉnh.
- [ ] Có cơ chế rollback có kiểm soát và phân biệt trường hợp khóa đã bị compromise (không overlap).
- [ ] Sau cutover + grace period, C_old bị loại khỏi mọi trust set, cache và artifact; signed-old negative test phải fail.
- [ ] Có giám sát expiry/refresh/rotation, chủ sở hữu và kịch bản thao tác khẩn cấp khi IdP signing key lộ.
- [ ] Không log raw SAMLResponse, private key, cookie hay dữ liệu cá nhân; chỉ audit mức cần thiết.
- [ ] Đóng change ticket bằng kết quả smoke tests và trạng thái cuối cùng `{C_new}`.

**Tóm lại:** Luân chuyển IdP signing certificate an toàn là một **quy trình phối hợp hai phía**, không chỉ là đổi tên một file X.509. IdP **công bố khóa mới trước khi sử dụng**, SP **chấp nhận hai public keys đã được xác minh trong giai đoạn giao nhau**, IdP **chuyển ký**, SP **quan sát và cuối cùng loại khóa cũ**. Trường hợp lộ private key phải xử lý như sự cố bảo mật và thu hồi ngay theo rủi ro, không kéo dài overlap. Spring Security cung cấp cơ chế nhiều verification credentials; phần **thời điểm, nguồn tin cậy, đồng bộ, kiểm thử và thu hồi** vẫn là trách nhiệm của hệ thống vận hành.

## 17. Tài liệu đối chiếu

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — `RelyingPartyRegistration`, asserting-party verification credentials, metadata và các endpoint.
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — parsing IdP metadata, `AssertingPartyMetadataRepository`, signature validation và refresh.
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) — xác minh assertions, provider và các điểm mở rộng.
- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) — sự khác biệt giữa SP signing credentials và asserting-party keys.
- [Spring Boot — SAML2 Relying Party Configuration](https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html) — cú pháp `assertingparty.verification.credentials`.
- [Microsoft Entra ID — Manage federation certificates](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/tutorial-manage-certificates-for-federated-single-sign-on) — hướng dẫn chuẩn bị khóa mới, dual certificate rollover và thời hạn.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html) — bảo vệ khóa ký và nguồn metadata.
- [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf) — `EntityDescriptor`, `KeyDescriptor` và metadata trust.
- [Java 17 CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html) — đọc certificate X.509 công khai.
- [Java 17 Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html) — API tạo và xác minh chữ ký trong demo mật mã.
