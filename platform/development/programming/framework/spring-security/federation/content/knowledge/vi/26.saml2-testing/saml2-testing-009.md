# Kiểm thử assertion mã hóa, thiếu thuộc tính và dữ liệu đa trị trong SAML 2.0

## 1. Mục tiêu và phạm vi

Trong **SAML 2.0 Web Browser SSO**, Service Provider (SP, ứng dụng Spring Security) tiếp nhận `SAMLResponse` từ Identity Provider (IdP), kiểm tra nguồn phát hành, chữ ký, thời gian, người nhận, audience và các điều kiện khác rồi mới thiết lập `Authentication`. Việc tích hợp có thể chạy tốt với một Assertion không mã hóa, một giá trị email và một nhóm đơn giản; nhưng khi IdP bật **`EncryptedAssertion`**, bỏ một thuộc tính hoặc gửi **nhiều `AttributeValue`**, những giả định trong mã application rất dễ gây đăng nhập thất bại, gán nhầm danh tính hoặc cấp quyền sai.

Bài thuộc nhóm **Kiểm thử SAML2** trong module **Spring Security - federation**. Ba mục tiêu chính:

1. **Assertion được mã hóa:** chứng minh SP giải mã được bằng đúng **private key của SP** mà không bỏ qua kiểm chữ ký, người nhận hoặc điều kiện SAML; kiểm lỗi key sai, thuật toán không hỗ trợ và quay vòng khóa.
2. **Thiếu thuộc tính:** phân biệt thiếu theo hợp đồng ứng dụng (ví dụ `tenant` bắt buộc), thuộc tính tùy chọn (ví dụ `displayName`), giá trị trống, nhiều giá trị mâu thuẫn và bản thân `NameID`; quyết định rõ **fail authentication** hay **authenticate nhưng deny authorization**.
3. **Dữ liệu đa trị:** đọc đúng danh sách giá trị của `Attribute`, xử lý nhóm một cách tối thiểu quyền, không dùng `getFirstAttribute` khi business rule phải xét toàn bộ danh sách, không chuyển các kiểu XML phức tạp thành role bằng `toString()`.

**Điều kiện an toàn:** các ví dụ XML dưới đây chỉ là sơ đồ/minh họa, **không phải SAMLResponse được ký thật**. Chỉ dùng IdP/test signing keys có kiểm soát để tạo fixtures E2E; không sửa raw XML rồi kỳ vọng nó còn chữ ký hợp lệ. Code Java 17 tự chạy ở phần sau chỉ mô phỏng **bước ánh xạ thuộc tính sau khi SAML đã được xác minh**, không tự giải mã hay kiểm chữ ký.

## 2. Ba lớp phải được kiểm thử tách biệt

| Lớp | Đang kiểm điều gì? | Thành phần thường chịu trách nhiệm |
| --- | --- | --- |
| **Cryptography & protocol authentication** | Decryption, signature, issuer, destination, recipient, audience, response correlation, time, replay | OpenSAML/Spring Security SAML2 provider |
| **Identity/attribute contract** | Có đúng `NameID`/subject ID, các attribute bắt buộc, đúng `Name`/`NameFormat`, cardinality và kiểu giá trị không? | IdP mappers và code business mapping phía SP |
| **Application authorization** | User active? đúng tenant? có group/role được phê duyệt? được truy cập resource nào? | `UserDetailsService`/policy service/authorization rules của ứng dụng |

Một Assertion được giải mã và ký đúng vẫn có thể **không có group cho ứng dụng**. Không nên coi đó là lỗi decrypt. Ngược lại, một Assertion có group `APP_ADMIN` nhưng chữ ký sai **không bao giờ được đưa tới code mapping role**.

### Luồng tổng quát

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant I as IdP
    participant A as Spring SP / ACS
    participant P as Local policy
    B->>I: AuthnRequest / SSO session
    I->>I: Tạo Assertion, ký theo policy
    I->>I: Encrypt Assertion/Attribute bằng public key SP
    I-->>B: SAMLResponse POST form
    B->>A: POST /login/saml2/sso/corp
    A->>A: Resolve RelyingPartyRegistration
    A->>A: Verify applicable signatures + decrypt
    A->>A: Validate subject, issuer, audience, recipient, time, replay
    A->>A: Expose verified NameID + attribute lists
    A->>P: Identity link, required fields, tenant và role allowlist
    P-->>A: Allowed authorities hoặc deny
    A-->>B: Session/redirect hoặc authentication/authorization failure
~~~

Vị trí kiểm chữ ký so với decrypt phụ thuộc **Response ký hay Assertion ký**, binding và thư viện. Không cố tái hiện tất cả bằng chuỗi code “giải mã XML trước, kiểm chữ ký sau” tự viết. Dùng Spring Security/OpenSAML provider được cấu hình đúng.

## 3. SAML Response, Assertion và các phần tử được mã hóa

Một response có thể chứa `<saml:Assertion>` dạng đọc được hoặc `<saml:EncryptedAssertion>`. Bên trong Assertion còn có thể gặp `<saml:EncryptedAttribute>` và `<saml:EncryptedID>`. Đây là **ba vị trí khác nhau**:

| Phần tử | Vị trí | Ý nghĩa | Decryption context |
| --- | --- | --- | --- |
| **`EncryptedAssertion`** | `samlp:Response` | Mã hóa nội dung cả Assertion | Response elements decrypter |
| **`EncryptedAttribute`** | `saml:AttributeStatement` | Chỉ một Attribute được mã hóa | Assertion elements decrypter |
| **`EncryptedID`** | `saml:Subject` hoặc ngữ cảnh cho phép | Mã hóa identifier/NameID | Assertion elements decrypter |

Theo tài liệu Spring Security **7.1**, `OpenSaml5AuthenticationProvider` dùng **hai chiến lược giải mã**: `setResponseElementsDecrypter` cho `EncryptedAssertion` và `setAssertionElementsDecrypter` cho `EncryptedAttribute`/`EncryptedID`. Mặc định Spring có thể giải mã tự động bằng những `Saml2X509Credential` loại **decryption** trong `RelyingPartyRegistration`.

**Không nhầm:** mã hóa **không thay thế** ký số và xác minh. Chữ ký có thể nằm ở Response hoặc Assertion, theo trust policy/profile; XML Encryption cung cấp confidentiality, XML Signature bảo vệ tính toàn vẹn/xuất xứ sau khi verify đúng. SAML Assertion có chữ ký nhưng không encrypt vẫn có thể lộ PII qua browser, log hoặc WAF.

### XML cấu trúc tối giản (không phải ciphertext hợp lệ)

~~~xml
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:xenc="http://www.w3.org/2001/04/xmlenc#"
                ID="_example-response" Version="2.0">
  <saml:Issuer>https://idp.example/metadata</saml:Issuer>
  <saml:EncryptedAssertion>
    <xenc:EncryptedData>
      <!-- Dữ liệu ciphertext thật do IdP tạo; không chèn XML giả vào ACS -->
    </xenc:EncryptedData>
    <!-- EncryptedKey và thuật toán do implementation hỗ trợ -->
  </saml:EncryptedAssertion>
</samlp:Response>
~~~

Skeleton thiếu trường bắt buộc, XML Signature, encrypted data/ciphertext và các điều kiện của profile, nên **không dùng làm fixture đăng nhập**. Nó chỉ cho biết vì sao SP không thể lấy `AttributeValue` bằng cách grep raw `SAMLResponse` khi IdP bật encryption.

## 4. Ai có public key, ai giữ private key?

SAML encryption trong kịch bản IdP → SP:

~~~text
Spring SP:
  owns private key + X.509 certificate for DECRYPTION
  exposes/shares matching public certificate (typically metadata)

IdP:
  reads trusted SP encryption certificate/public key
  encrypts Assertion/Attribute intended for that SP

Browser:
  carries encrypted SAMLResponse to SP

Spring SP:
  uses own PRIVATE key to decrypt
  verifies IdP signatures using IdP public verification certificate
  validates issuer/audience/recipient/time/replay
~~~

**Hai bộ khóa có vai trò khác nhau:**

- **IdP signing key:** IdP ký; **SP lưu public verification certificate** để kiểm chữ ký.
- **SP decryption key:** IdP encrypt bằng **public certificate của SP**; SP giữ **private decryption key**.
- Nếu SP còn ký `AuthnRequest`, đó là **signing credential của SP** (có thể trùng hoặc khác decryption key theo chính sách).
- Không gửi SP private key tới IdP và không commit vào Git, log, test report, support ticket.
- Chữ ký X.509 và mã hóa XML có thể dùng certificate khác nhau; đừng gọi mọi file `idp.crt` là “decryption cert”.

### Sai key thường dẫn tới điều gì?

Nếu IdP đã encrypt bằng public key A nhưng Spring chỉ có private key B, decrypt phải **FAIL** và không phát authenticated session. Nếu có hai registrations/tenants, private keys phải gắn với đúng `RelyingPartyRegistration`, không thử “mọi tenant key” một cách không kiểm soát và rồi gán sai issuer.

**Không giải lỗi bằng việc tắt signature validation, bỏ audience checks hoặc chấp nhận raw XML để lấy NameID.**

## 5. Quy trình xử lý của Spring Security/OpenSAML

Tài liệu Spring Security SAML2 mô tả luồng tiêu biểu:

1. `Saml2WebSsoAuthenticationFilter` nhận HTTP POST có `SAMLResponse` tại ACS, thường `/login/saml2/sso/{registrationId}`.
2. Resolver/`AuthenticationConverter` xác định đúng `RelyingPartyRegistration` và tạo token xác thực ban đầu.
3. `OpenSaml5AuthenticationProvider` xử lý Response với các chiến lược kiểm chữ ký và decryption phù hợp.
4. Nếu có `EncryptedAssertion`, phần đó được giải mã bằng **SP decryption credential** tương ứng.
5. Provider xác minh Response/Assertion signature theo quy tắc của profile và issuer đã đăng ký; decryption các `EncryptedAttribute`/`EncryptedID` diễn ra vào vị trí thích hợp với chữ ký.
6. Kiểm `Issuer`, `Destination`, `Recipient`, `InResponseTo`, `AudienceRestriction`, `Conditions` và `SubjectConfirmationData` time window phù hợp profile, cùng replay protection nếu ứng dụng yêu cầu.
7. Chỉ sau khi authentication hợp lệ, provider xây `Authentication` và dữ liệu thuộc tính để code local mapping sử dụng.
8. Local policy kiểm **account link + tenant/roles**; thiếu quyền phải fail closed.

**Lưu ý phiên bản:** ở Spring Security 6 nhiều ví dụ dùng `OpenSaml4AuthenticationProvider` và `Saml2AuthenticatedPrincipal`. Spring Security 7 dùng `OpenSaml5AuthenticationProvider` trong reference hiện hành và giới thiệu `Saml2AssertionAuthentication`/`Saml2ResponseAssertionAccessor`, đồng thời đánh dấu `Saml2AuthenticatedPrincipal` deprecated. Không copy class/provider từ blog 5.x sang dự án 7.x mà không kiểm dependency tree.

### Vì sao có hai giai đoạn decryption?

Khi Assertion được ký, decrypt một `EncryptedAttribute` **trước khi kiểm chữ ký Assertion** có thể làm thay đổi nội dung XML đã ký, dẫn đến sai validation hoặc mở ra một trust boundary không đúng. Spring tách response decrypter và assertion decrypter để giữ trình tự xử lý phù hợp. Nếu chỉ Response được ký, chiến lược decryption có thể khác, nhưng **không tự viết một pipeline bỏ qua signature** để “lấy attributes sớm”.

## 6. Cấu hình SP decryption credential ở Spring Security

Đây là **fragment Java trong dự án Spring Security SAML2**, không phải Java 17 standalone; project cần `spring-security-saml2-service-provider`, OpenSAML dependency tương thích và IdP metadata thật. Code minh họa API `RelyingPartyRegistration`/`Saml2X509Credential`:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.cert.X509Certificate;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

public class SamlDecryptionRegistrationExample {

    RelyingPartyRegistration registration(
            RSAPrivateKey spPrivateKey,
            X509Certificate spEncryptionCertificate) {

        Saml2X509Credential decryptCredential =
                Saml2X509Credential.decryption(
                        spPrivateKey, spEncryptionCertificate);

        return RelyingPartyRegistrations
                .fromMetadataLocation(
                    "https://idp.example/metadata")
                .registrationId("corp")
                .decryptionX509Credentials(
                    credentials -> credentials.add(decryptCredential))
                .build();
    }
}
~~~

**Phải bổ sung trong ứng dụng thật:** load private key từ secret manager/mounted secret dưới quyền tối thiểu; load certificate tương ứng; trust và pin/review IdP metadata/signing certificates; tạo `RelyingPartyRegistrationRepository`; cấu hình `SecurityFilterChain` với `saml2Login`; kiểm HTTPS, host/ACS/EntityID và metadata/key rotation. Đoạn trên không tự tạo `AuthenticationManager` hay IdP metadata và **không được copy private key vào source code**.

**Kiểm API theo Spring version:** `RelyingPartyRegistrations.fromMetadataLocation(...)` và `decryptionX509Credentials(...)` có trong tài liệu hiện hành. Spring Boot cũng có cấu hình property cho credential locations, nhưng đường dẫn property/kiểu load có thể khác theo Boot version. Không tự đoán YAML property từ ví dụ Java nếu chưa đối chiếu đúng phiên bản đang dùng.

### Thành phần cần giữ độc lập

~~~text
SP's own decryption private key:
  file:/run/secrets/saml/corp-decrypt.pkcs8 (private)

SP matching X.509 public certificate:
  file:/etc/saml/corp-decrypt.crt (public)
  => IdP uses this certificate to encrypt for SP

IdP verification certificate:
  from reviewed IdP metadata / trusted signing keys
  => Spring uses it to verify IdP signature

IdP signing private key:
  stays on the IdP, NEVER in Spring SP
~~~

**Đừng nhầm certificate là đủ để decrypt**: giải mã cần **private key**, không chỉ public certificate. Khi metadata IdP và SP cùng có nhiều `KeyDescriptor`, xem thuộc tính `use="encryption"`/`use="signing"` và product support, không chỉ nhìn alias file giống nhau.

## 7. Test decryption theo ma trận khóa, thuật toán và metadata

| Ca | Fixture/thiết lập | Kỳ vọng |
| --- | --- | --- |
| E1 | IdP encrypt bằng SP public key A; SP có private A | Decrypt thành công; **vẫn phải** validate SAML |
| E2 | IdP encrypt bằng A; SP chỉ có private B | Authentication FAIL, không cấp session |
| E3 | Private key đúng nhưng cert/metadata cấu hình sai | Không tự chọn nhầm key; lỗi rõ ở decrypt/registration |
| E4 | `EncryptedAssertion` hợp lệ, signature/Audience đúng | Login + mapping trong phạm vi policy |
| E5 | `EncryptedAttribute` thuộc nhóm trong Assertion ký | Decrypt đúng thứ tự sau signature checks |
| E6 | `EncryptedID` cho `NameID` | Principal identity lấy đúng sau decrypt/validation |
| E7 | Signature IdP sai nhưng decrypt được | Authentication FAIL; decrypt success không là trusted auth |
| E8 | EncryptedAssertion bị chỉnh ciphertext | Decrypt/crypto integrity FAIL; không grant role |
| E9 | IdP dùng algorithm không được baseline/stack hỗ trợ | Reject theo policy; không bật weak crypto |
| E10 | Metadata có encryption cert A; IdP chưa cập nhật | Nêu lỗi phối hợp/rotation, không “decrypt ignore error” |
| E11 | Có old+new decryption keys trong rollout | Chấp nhận fixtures encrypt bằng cert còn hợp lệ theo policy |
| E12 | Old cert đã retire | Không âm thầm tiếp tục decrypt bằng key đáng lẽ đã xóa |
| E13 | Hai SP tenants có keys/EntityIDs khác | Không giải bằng key tenant khác hoặc liên kết sai user |
| E14 | Có plaintext Assertion ngoài ý muốn khi policy bắt buộc encryption | Enforce policy tại IdP/SP/hạ tầng phù hợp, không mặc định Spring reject plaintext nếu chưa cấu hình |
| E15 | Response có nhiều Assertions, một invalid | Không chọn một cái hợp lệ rồi bỏ qua cái khác mà thiếu profile-specific checks |

**Phân biệt hai khái niệm:** “IdP bật encrypt” không đồng nghĩa SP mặc định **bắt buộc** mọi Assertion đều encrypted. Nếu doanh nghiệp yêu cầu *encryption mandatory*, phải có policy/validation có kiểm chứng tại SP/gateway/IdP; việc cấu hình private key chỉ làm SP **có thể decrypt**, không tự chứng minh policy luôn được enforce.

### Thuật toán và bảo mật XML Encryption

Chọn tổ hợp **XML Encryption** và key transport đang được IdP/OpenSAML/SP hỗ trợ, theo crypto baseline; ưu tiên các thuật toán hiện đại có interoperability (ví dụ RSA-OAEP để wrap key, AES-GCM nếu được stack hỗ trợ). Tránh bật legacy yếu như RSA v1.5 key transport chỉ để vượt lỗi interop mà không có security assessment.

**Không tự implement XML Encryption bằng DOM + Cipher ngẫu nhiên.** SAML/XmlSec/OpenSAML phải xử lý reference, encrypted keys, algorithm restrictions, XML canonicalization, signatures và parsing an toàn. Hạn chế XML parser external entities/DTD/XXE, kích thước request/ciphertext, mức sâu XML và số phần tử để tránh memory/CPU abuse.

## 8. Key rotation và multi-instance: lỗi thường khó phát hiện

Quay vòng SP decryption key thường cần **thời gian overlap**:

~~~text
T0: SP advertises encryption public cert A, holds private A
T1: SP publishes cert B along with A when supported
T2: IdP switches to encrypting with B
T3: SP replicas still hold A and B for in-flight messages
T4: After safe overlap and verification, retire A
~~~

Không mọi IdP xử lý nhiều encryption certificates giống nhau. Thời gian overlap phải dựa trên thực tế **metadata caching, InResponseTo/outstanding AuthnRequests, assertion/ticket TTL, deployment lag** và chính sách an ninh. Kiểm khi scale:

- Pod A có cả keys A+B, pod B chỉ có A → login ngẫu nhiên fail theo load balancer.
- IdP vừa đổi cert B nhưng metadata registry ở SP chưa cập nhật.
- Admin rotate **IdP signing cert**, nhưng đội ứng dụng tưởng là **SP encryption key**.
- Các tenants chung một private key ngoài ý muốn, làm tăng blast radius.
- Private key ở container image/log/build artifact, không được revoke đồng thời.

**Test E2E cả key cũ/new trong cửa sổ chuyển đổi**, log lỗi với high-level code (DECRYPTION_FAILED/KEY_MISMATCH), không dump raw `SAMLResponse` hay key bytes.

## 9. AttributeStatement: SAML hỗ trợ nhiều AttributeValue

Theo OASIS SAML Core, mỗi `<saml:Attribute>` có **`Name` bắt buộc**, có thể có `NameFormat`, `FriendlyName` và **0..N `<saml:AttributeValue>`**. Nếu chứa nhiều giá trị rời rạc, mỗi giá trị nên ở phần tử `AttributeValue` riêng. `AttributeValue` dựa trên `xs:anyType`, nên **không mặc định mọi giá trị đều là String**.

Minh họa **bên trong một Assertion plaintext hợp lệ về mặt ý tưởng thuộc tính**, chưa có chữ ký/timestamp/subject confirmation nên không được POST thẳng vào ACS:

~~~xml
<saml:AttributeStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <saml:Attribute Name="urn:example:claims:groups"
                  NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
                  FriendlyName="groups">
    <saml:AttributeValue xsi:type="xs:string">APP_REPORT_VIEWERS</saml:AttributeValue>
    <saml:AttributeValue xsi:type="xs:string">FINANCE_EMPLOYEES</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="urn:example:claims:tenant">
    <saml:AttributeValue xsi:type="xs:string">reports</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="urn:example:claims:email">
    <saml:AttributeValue xsi:type="xs:string">lan@example.test</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
~~~

**Ba bẫy điển hình:**

1. `FriendlyName="groups"` là tên hiển thị gợi ý; application contract phải dựa vào **Name/NameFormat đã phê duyệt**, không tự tin vào FriendlyName do một assertion chưa kiểm gửi.
2. Một nhóm **không nhất thiết** được trình bày bằng chuỗi phân tách dấu phẩy; chuẩn SAML đa trị sử dụng **nhiều AttributeValue**. Nếu IdP của bạn phát `"role1,role2"` làm một value, hãy mô tả chính xác contract riêng thay vì tự split mọi string.
3. `Name="groups"` và `Name="urn:example:claims:groups"` là hai identifiers khác nhau nếu hợp đồng không khai báo alias tương ứng. Không tự fallback qua một tên có vẻ giống.

### XML không có AttributeValue nghĩa là gì?

OASIS mô tả `Attribute` với **không có `AttributeValue`** trong một `AttributeStatement` là một tình huống có semantics riêng; không nên tự hiểu thành `null`, empty string, quyền mặc định hay “IdP muốn mọi giá trị”. `AttributeQuery` có quy tắc khác về absence of values. Trong ứng dụng, cần định nghĩa rõ **missing vs present-but-empty vs blank value**.

## 10. Contract của thuộc tính: bắt buộc, tùy chọn và đa trị

Một service Reports có thể có contract như sau (các tên claim là ví dụ):

| Claim | Cardinality | Chính sách |
| --- | --- | --- |
| **NameID/subject ID** | 1 định danh ổn định theo trusted IdP/NameIDFormat | Không có/không hợp lệ: authentication hoặc identity-link fail |
| **`urn:example:claims:tenant`** | **Exactly one** nonblank string | Thiếu/2 giá trị/mâu thuẫn: deny, không chọn first |
| **`urn:example:claims:groups`** | 0..N strings | Missing/empty: authenticated user có thể tồn tại nhưng **không có app role** |
| **`urn:example:claims:email`** | 0..1 string | Thiếu: cho login nếu không cần; không dùng làm identity key |
| **`urn:example:claims:displayName`** | 0..1 string | Missing: hiển thị tên local/fallback không nhạy cảm |
| **`urn:example:claims:department`** | 0..1 hoặc 0..N theo contract | Không suy quyền truy cập từ dữ liệu chưa phê duyệt |
| **`urn:example:claims:roles`** | 0..N strings từ issuer được tin | Chỉ map allowlisted roles; unknown values bỏ qua/deny theo policy |

**“Bắt buộc” ở bảng này là **hợp đồng nghiệp vụ**, không phải đương nhiên SAML 2.0 Core bắt buộc IdP phải trả field `email`/`groups`/`tenant`**. Một SP có thể xác thực SAML hợp lệ mà không có AttributeStatement; sau đó application từ chối tác vụ do thiếu dữ liệu phân quyền. Cần thống nhất chính sách login và quyền cho từng use case, tránh báo login failure nếu chỉ thiếu field hiển thị.

### Ma trận null/empty/blank

| Dữ liệu quan sát sau validate | Ví dụ | Cách ứng dụng xử lý |
| --- | --- | --- |
| Attribute không có | Không có `tenant` trong Map | Deny nếu required; fallback nếu optional |
| Attribute có nhưng không values | `tenant -> []` | Deny required; **khác** việc không có |
| Một string rỗng | `tenant -> [""]` | Deny required |
| Whitespace | `tenant -> ["   "]` | Deny; trim/canonicalization chỉ nếu IdP contract cho phép |
| Một giá trị hợp lệ | `tenant -> ["reports"]` | Accept nếu trusted issuer và policy |
| Hai giá trị giống nhau | `tenant -> ["reports", "reports"]` | **Deny cardinality** nếu field chỉ được 1; không tự deduplicate |
| Hai giá trị trái nhau | `tenant -> ["reports", "finance"]` | Deny, không `getFirstAttribute` |
| Giá trị XML typed non-string | `tenant -> [42]` | Deny nếu schema yêu cầu string |
| Group list nhiều values | `groups -> ["APP_REPORT_VIEWERS","OtherGroup"]` | Map approved group, bỏ unknown group theo policy |
| Group bị thiếu | `groups -> null` | Không cấp role mặc định |
| Group non-string/huge | `groups -> [complex XML]` | Deny/record validation error theo contract |

**Lý do phải test cả missing và empty:** thư viện hay IdP mapper có thể biểu diễn `Attribute` không giá trị khác với attribute vắng mặt; code `getFirstAttribute("tenant").toString()` có thể ném NullPointerException, hoặc trả phần tử đầu và vô tình bỏ các giá trị mâu thuẫn.

## 11. Vai trò, nhóm và nguyên tắc tối thiểu quyền

Giả sử IdP phát nhóm:

~~~text
["Domain Admins", "APP_REPORT_VIEWERS", "UnrelatedTeam"]
~~~

Ứng dụng Reports chỉ có mapping được phê duyệt:

~~~text
IdP attribute Name: urn:example:claims:groups
value "APP_REPORT_VIEWERS" -> ROLE_REPORT_VIEWER
value "APP_REPORT_EDITORS" -> ROLE_REPORT_EDITOR
value "Domain Admins" -> NO APP AUTHORITY
unknown values -> NO APP AUTHORITY, optionally audit safe code
~~~

**Không làm:** bất kỳ string chứa `Admin` → `ROLE_ADMIN`, lấy value đầu của list rồi coi là role, hay dùng `String.join(",", groupValues)` rồi tìm substring `"ADMIN"`. Nếu group dùng DNs, URI identifiers hoặc GUIDs, chuẩn hóa theo **namespace được phê duyệt**, không regex tự do.

Các thuộc tính **identity-critical** (stable subject, tenant) nên có cardinality chặt; còn groups thường có **0..N** với mapping allowlist. Không cần coi 20 group là 20 lần login, nhưng phải giới hạn kích thước list, độ dài giá trị và xử lý duplicate/nested memberships.

### Group claim không tự cấp authority

Spring Security SAML2 provider có thể cấp `ROLE_USER` hoặc factor authority mặc định theo phiên bản. Đó **không** là quyền xem báo cáo. **Application-specific roles** cần mapping hoặc tra cứu local entitlement. Test rằng user có SAML Authentication nhưng không có group được duyệt **không truy cập** endpoint cần `ROLE_REPORT_VIEWER`.

## 12. Spring Security 6 so với 7: đọc thuộc tính ở đâu?

**Spring Security 5/6:** sau SAML login, nhiều code dùng `Saml2AuthenticatedPrincipal`, có API:

~~~java
// Spring Security 5/6 pattern; fragment trong app có SAML auth hợp lệ.
Saml2AuthenticatedPrincipal principal = ...;
String email = principal.getFirstAttribute("email");
java.util.List<String> groups = principal.getAttribute("groups");
// getAttributes() có kiểu Map<String, List<Object>>.
~~~

**Lưu ý:** `getFirstAttribute` tiện cho field **được contract đảm bảo đúng một giá trị**; không được dùng nó để “hợp thức hóa” tenant khi IdP gửi hai tenant hay để lấy chỉ một group nếu cần toàn bộ.

**Spring Security 7:** tài liệu migration đánh dấu `Saml2AuthenticatedPrincipal` deprecated và ưu tiên **`Saml2AssertionAuthentication`** với **`Saml2ResponseAssertionAccessor`**. Accessor giữ `getAttributes()` trả `Map<String, List<Object>>`, `getAttribute(name)` trả list và `getFirstAttribute(name)` trả value đầu (hoặc null). Theo API 7, accessor có thể nằm trong `Authentication.getCredentials()`; ứng dụng lấy type/contract phù hợp thay vì ép principal luôn thuộc type cũ.

~~~java
// Fragment minh họa trong Spring Security 7 sau xác thực:
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2ResponseAssertionAccessor;

void inspectVerifiedAttributes(Authentication authentication) {
    Object credentials = authentication.getCredentials();
    if (credentials instanceof Saml2ResponseAssertionAccessor accessor) {
        java.util.Map<String, java.util.List<Object>> attrs =
                accessor.getAttributes();
        java.util.List<Object> groups =
                attrs.get("urn:example:claims:groups");
        // Chỉ map sau khi authentication là kết quả của provider đã validate;
        // required/optional policy ở tầng ứng dụng.
    }
}
~~~

Đoạn trên là **integration fragment**, không phải standalone Java. Tùy converter, custom Authentication và minor version, credentials/principal type có thể khác; **kiểm actual class và Javadoc của resolved dependency**. Không cast mọi Authentication về `Saml2AssertionAuthentication` khi ứng dụng có các cơ chế login khác.

**Tránh anti-pattern:** `authentication.getCredentials().toString()` hoặc `authentication.getSaml2Response()` để log/debug; dữ liệu có thể chứa raw Assertion và PII. Không tự deserialize XML chưa xác minh từ request body để lấy groups trước Spring Security provider.

## 13. Kỹ thuật map thuộc tính sau validation

Thiết kế mapper nhận một input đã được provider kiểm:

~~~text
Authenticated context (trusted SP/IdP registration + NameID)
  + Map<String, List<Object>> verified attributes

Step 1: require expected trusted issuer/registration
Step 2: validate stable subject and identity-link
Step 3: require tenant cardinality=1, string nonblank
Step 4: allow optional email/displayName absent
Step 5: validate group list 0..N, values typed strings and bounded
Step 6: exact-match approved group IDs -> application authorities
Step 7: consult local active user, tenant and business permission
Step 8: deny if no entitled authority or wrong resource tenant
~~~

Không dùng **một custom attribute mapper** để thay provider signature/audience/timestamp/replay validation. Custom mapping phải chạy **sau** trusted authentication context hoặc trong một converter chỉ được provider gọi sau các checks được document bảo đảm.

Để phân biệt **signing failure** và **business attribute failure**, sử dụng error codes:

~~~text
SAML_SIGNATURE_INVALID
SAML_DECRYPTION_FAILED
SAML_AUDIENCE_MISMATCH
SAML_TIME_INVALID
SAML_REPLAY_DETECTED
ATTR_REQUIRED_MISSING
ATTR_CARDINALITY_INVALID
ATTR_VALUE_TYPE_INVALID
APP_GROUP_NOT_APPROVED
APP_TENANT_ACCESS_DENIED
~~~

**Không đưa giá trị SAMLResponse, key, NameID, group list đầy đủ hoặc decoded XML vào audit log**; log safe error class, registration ID đã xác minh, correlation ID độc lập và latency.

## 14. Java 17 tự chạy: contract cho thuộc tính sau SAML validation

Ví dụ sau dùng **Java 17 chuẩn, không cần thư viện bên ngoài**, mô phỏng `Map<String,List<?>>` sau khi SAML được **giả định** đã kiểm chữ ký/issuer/audience/time và được giải mã. **Đây không phải SAML verifier hoặc XML decrypter**. Mục đích: kiểm required tenant vs optional email, group multi-values, data type và authorization.

Tạo file **`SamlAttributesContractDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class SamlAttributesContractDemo {

    static final String TRUSTED_IDP = "https://idp.example/metadata";

    record Identity(
            String issuer,
            String subject,
            Map<String, List<?>> attrs) { }

    static Map<String, List<?>> attrs(
            List<?> tenant,
            List<?> groups,
            List<?> email) {
        Map<String, List<?>> result = new HashMap<>();
        if (tenant != null) result.put("tenant", tenant);
        if (groups != null) result.put("groups", groups);
        if (email != null) result.put("email", email);
        return result;
    }

    static Identity user(Map<String, List<?>> values) {
        return new Identity(TRUSTED_IDP, "user-041", values);
    }

    static String decide(Identity input) {
        // The real SAML provider MUST validate this before mapping.
        if (!TRUSTED_IDP.equals(input.issuer())) {
            return "DENY: issuer";
        }
        if (input.subject() == null || input.subject().isBlank()) {
            return "DENY: subject";
        }

        List<?> tenant = input.attrs().get("tenant");
        if (tenant == null || tenant.isEmpty()) {
            return "DENY: tenant missing";
        }
        if (tenant.size() != 1
                || !(tenant.get(0) instanceof String value)
                || value.isBlank()) {
            return "DENY: tenant cardinality";
        }
        if (!"reports".equals(value)) {
            return "DENY: tenant mismatch";
        }

        List<?> groups = input.attrs().get("groups");
        if (groups == null || groups.isEmpty()) {
            return "DENY: no approved role";
        }
        if (groups.size() > 16) {
            return "DENY: group list too long";
        }

        boolean hasApprovedGroup = false;
        for (Object element : groups) {
            if (!(element instanceof String group)
                    || group.isBlank()
                    || group.length() > 128) {
                return "DENY: invalid group value";
            }
            if ("APP_REPORT_VIEWERS".equals(group)) {
                hasApprovedGroup = true;
            }
        }
        return hasApprovedGroup
                ? "ALLOW: ROLE_REPORT_VIEWER"
                : "DENY: no approved role";
    }

    public static void main(String[] args) {
        Map<String, List<?>> basic = attrs(
                List.of("reports"),
                List.of("APP_REPORT_VIEWERS"),
                List.of("lan@example.test"));

        System.out.println("Valid: " + decide(user(basic)));

        System.out.println("Missing optional email: "
                + decide(user(attrs(
                    List.of("reports"),
                    List.of("APP_REPORT_VIEWERS"),
                    null))));

        System.out.println("Multi-valued groups: "
                + decide(user(attrs(
                    List.of("reports"),
                    List.of("Domain Admins", "APP_REPORT_VIEWERS"),
                    null))));

        System.out.println("Missing tenant: "
                + decide(user(attrs(
                    null, List.of("APP_REPORT_VIEWERS"), null))));

        System.out.println("Two tenants: "
                + decide(user(attrs(
                    List.of("reports", "finance"),
                    List.of("APP_REPORT_VIEWERS"), null))));

        System.out.println("Wrong tenant: "
                + decide(user(attrs(
                    List.of("finance"),
                    List.of("APP_REPORT_VIEWERS"), null))));

        System.out.println("Unapproved groups: "
                + decide(user(attrs(
                    List.of("reports"),
                    List.of("Domain Admins"), null))));

        System.out.println("Non-string group: "
                + decide(user(attrs(
                    List.of("reports"),
                    List.of(7), null))));

        System.out.println("Wrong issuer: "
                + decide(new Identity(
                    "https://other.example/metadata",
                    "user-041", basic)));

        System.out.println("Blank subject: "
                + decide(new Identity(
                    TRUSTED_IDP, "", basic)));

        System.out.println("External admin promoted: "
                + decide(user(attrs(
                    List.of("reports"),
                    List.of("Domain Admins"), null))
                    .contains("ROLE_ADMIN"));
    }
}
~~~

Lệnh chạy với JDK 17 trở lên:

~~~bash
javac SamlAttributesContractDemo.java
java SamlAttributesContractDemo
~~~

**Stdout chính xác:**

~~~text
Valid: ALLOW: ROLE_REPORT_VIEWER
Missing optional email: ALLOW: ROLE_REPORT_VIEWER
Multi-valued groups: ALLOW: ROLE_REPORT_VIEWER
Missing tenant: DENY: tenant missing
Two tenants: DENY: tenant cardinality
Wrong tenant: DENY: tenant mismatch
Unapproved groups: DENY: no approved role
Non-string group: DENY: invalid group value
Wrong issuer: DENY: issuer
Blank subject: DENY: subject
External admin promoted: false
~~~

**Phân tích:**

- **Valid:** tenant đúng và có group được cấp quyền → role application được cấp trong **mô hình**.
- **Missing optional email:** không ảnh hưởng authorization nếu email chỉ dùng hiển thị.
- **Multi-valued groups:** không lấy giá trị đầu `Domain Admins` làm ROLE_ADMIN; vẫn tìm được value được cho phép.
- **Missing/Two tenants:** thiếu hoặc có nhiều giá trị cho field cardinality 1 đều từ chối.
- **Wrong tenant:** ngay cả group đúng cũng không cho xem resource của tenant khác.
- **Unapproved groups:** có dữ liệu group nhưng không có entitlement app → deny.
- **Non-string group:** không gọi `toString()` trên giá trị kiểu khác rồi tạo role.
- **Wrong issuer/Blank subject:** fail trong mô hình, nhưng thực tế issuer phải được **OpenSAML provider xác minh bằng signing certificates**, không phải chỉ so chuỗi như demo.
- **External admin promoted:** `Domain Admins` không tự thành quyền admin của Reports app.

Đây là kiểm thử **mapping contract**, không kiểm thực sự `EncryptedAssertion`. Muốn kiểm crypto phải dùng SAML fixture được ký/mã hóa bằng **bộ khóa lab** và đưa qua Spring filter/IdP thực, không gọi hàm demo rồi tuyên bố decryption PASS.

## 15. Cách tạo fixtures SAML2 có ý nghĩa kiểm thử

**Không tự chỉnh plaintext XML sau khi đã ký** để tạo case “thiếu attribute”. Làm vậy sẽ làm signature sai, nên test có thể fail ở signature validation **trước khi** chạy logic thuộc tính; đó không phải bằng chứng phần handling missing attribute hoạt động.

Quy trình đúng khi có IdP test:

1. Tạo SP test EntityID/ACS và public encryption certificate riêng của lab.
2. Cấu hình IdP test phát SAMLResponse với signing policy đúng và public cert SP.
3. Tạo **base fixture** có subject, valid Conditions, SubjectConfirmationData, audience, response correlation, signature và attrs như contract.
4. Với mỗi ca thuộc tính, thay đổi **IdP mapper/test data trước lúc IdP ký/mã hóa**, hoặc dùng thư viện SAML test để tái tạo và ký/mã hóa lại toàn bộ SAMLResponse.
5. Gửi HTTP POST thật tới ACS của Spring ở staging, qua cùng reverse proxy/binding với production.
6. Kiểm Spring provider đã xác thực hay từ chối, rồi kiểm local roles/tenant.
7. Với ca encryption failure, giữ attributes/signature hợp lệ nhưng mã hóa bằng **một SP public certificate khác** trong lab để tách lỗi key mismatch.
8. Không dùng production signing/decryption private keys trong pipeline CI hoặc public fixtures.
9. Không commit raw SAMLResponses chứa NameID/PII thật; dùng test identities, secrets và certificates riêng có thời hạn.
10. Sau test, xóa credential artifacts trong logs/HAR/test reports theo chính sách.

### Bốn nhóm fixture chính

| Nhóm | Cách sinh | Kiểm điều gì? |
| --- | --- | --- |
| **Crypto positive** | IdP ký + encrypt với SP public key đúng | SP decrypt, verify, authenticated và map quyền đúng |
| **Crypto negative** | IdP ký hợp lệ nhưng encrypt bằng key không tương ứng SP | Fail tại decryption, không tạo session |
| **Attribute positive** | IdP phát valid signed encrypted assertion với missing **optional** field hoặc multiple groups | Vẫn authenticate, mapper policy xử lý đúng |
| **Attribute negative** | IdP phát valid signed encrypted assertion thiếu **required** field hoặc type/cardinality sai | Crypto succeeds nhưng local policy reject |

**Bắt buộc chứng minh vị trí lỗi**: “SAML failed” chỉ là triệu chứng chung. Test missing tenant chỉ đạt mục tiêu nếu **signature/decryption đã thành công**, sau đó app từ chối vì tenant missing; nếu signature invalid, test đó **không kiểm** missing tenant.

## 16. Test theo tầng: unit, provider integration, end-to-end

### Unit test cho business mapping

Đầu vào: một `Map<String,List<Object>>` hoặc interface được kiểm kiểu, chủ thể và trusted IdP registration đã được **giả lập là đã xác thực**.

- Missing optional email → không gây NPE.
- Missing tenant → deny.
- Two tenants → deny.
- Groups list chứa nhiều giá trị → xử lý đầy đủ.
- Wrong data type → deny theo schema.
- Unknown group → không có role.
- Duplicate groups → không tăng quyền.
- Blank NameID/identity key → deny.
- Test null list, empty list, whitespace, Unicode và oversized input.

**Mock business mapping test không thay crypto test** vì không có chữ ký, encryption key hoặc XML parser trong input.

### Provider/Spring integration test

- Sử dụng **Spring Security SAML2 provider thật** và test IdP/OpenSAML fixture builder.
- Kiểm `RelyingPartyRegistrationRepository`, verification/decryption credentials và ACS endpoint.
- POST `SAMLResponse` (base64) qua đúng HTTP binding vào `Saml2WebSsoAuthenticationFilter`.
- Kiểm user authentication context, failure redirect/status và SecurityContext không bị set khi decrypt/signature fail.
- Kiểm local authority mapping và requestMatchers cho resource.
- Không log `SAMLResponse`, decoded Assertion XML hoặc private key vào test output.
- Kiểm tests chạy trên **resolved Spring Security/OpenSAML versions** thay vì dựa trên import cũ.

### E2E browser + IdP

- Browser/IdP thực, SAML HTTP POST auto-submit, reverse proxy, key rotation và metadata discovery.
- Kiểm cookie `SameSite` đối với cross-site POST ACS, `Secure`/`HttpOnly`, CSRF exceptions đúng cơ chế SAML.
- Quan sát network từ proxy/WAF đến Spring, xem có component log raw SAMLResponse không.
- Kiểm multi-instance deployments cùng secret/key versions.
- Kiểm browser session bị từ chối khi identity/tenant không hợp lệ.
- Kiểm replay cùng Assertion ID/Response ID trong cửa sổ test.

**Không mặc định mọi missing required claim phải trả HTTP 401.** Nếu SAML provider đã authenticate nhưng app thiếu role, route có thể trả **403**. Nếu custom authentication converter từ chối contract ngay từ auth step, có thể là login failure/redirect hoặc 401. Test cần xác định expected stage, **không hardcode HTTP status mà chưa cấu hình failure handler**.

## 17. Ma trận tích hợp chi tiết: mã hóa và khóa

| ID | Ca kiểm thử | Tiêu chí PASS |
| --- | --- | --- |
| C01 | `EncryptedAssertion` đúng key, ký đúng | Decrypt + verify + validation rồi authenticated |
| C02 | `EncryptedAssertion` sai SP key | Không tạo Authentication/session; báo lỗi decrypt an toàn |
| C03 | Thiếu private decryption key | Fail closed, không chuyển sang plaintext parser |
| C04 | SP certificate khác private key | Cấu hình/crypto fail; keypair mismatch được chẩn đoán |
| C05 | IdP signing certificate không nằm trust set | Fail signature check dù decrypt được |
| C06 | Signed Response + EncryptedAssertion | Verify đúng profile/issuer rồi xử lý |
| C07 | Signed Assertion được encrypt | Decrypt để có Assertion, verify signature phù hợp |
| C08 | `EncryptedAttribute` nhưng `Assertion` plaintext ký hợp lệ | Verify + decrypt theo đúng thứ tự của provider |
| C09 | `EncryptedID` chứa NameID | Subject mapping đúng sau decrypt |
| C10 | Corrupted CipherValue / EncryptedKey | Không fallback thành authenticated |
| C11 | Legacy encryption algorithm bị cấm | Reject theo security baseline |
| C12 | AES/key transport unsupported | Reject, nêu khả năng tương thích, không tự bật weak crypto |
| C13 | Old/new decryption keys trong rotation | Nhận chỉ những cert/key được policy cho phép |
| C14 | Pod A và Pod B dùng khác keyset | E2E test phát hiện drift trước rollout |
| C15 | Key tenant A dùng decrypt tenant B | Không gán nhầm realm/registration và không cross-tenant leakage |
| C16 | Plaintext Assertion khi tổ chức yêu cầu encryption | Policy enforcement phát hiện/deny nếu đã thiết kế bắt buộc |
| C17 | Response decrypted nhưng audience sai | Fail protocol validation |
| C18 | Response expired hoặc NotBefore trong tương lai | Fail theo time/skew policy |
| C19 | InResponseTo không khớp login request | Reject theo SP-initiated flow policy |
| C20 | Replay signed Assertion/Response cũ | Reject với replay detection phù hợp |
| C21 | XML có DTD/external entity/oversized structure | Parser giới hạn và từ chối theo policy |
| C22 | Mất key trong secret mount hoặc wrong permission | Fail + monitoring; không hạ file permissions rộng |

**Không tự đưa plaintext XML vào provider sau decrypt rồi bypass bước signature** trong một test helper. Test phải đảm bảo **đúng cơ chế library thực** được exercise.

## 18. Ma trận thuộc tính thiếu, rỗng và đa trị

| ID | Dữ liệu IdP đã ký đúng | Kỳ vọng local mapping |
| --- | --- | --- |
| A01 | Tenant 1 value, approved group 1 value | Role Viewer, đúng tenant |
| A02 | Email missing, tenant/group hợp lệ | Không login fail chỉ vì email không cần |
| A03 | DisplayName missing | Fallback UI approved, không mất subject |
| A04 | AttributeStatement vắng hoàn toàn | SAML auth có thể hợp lệ; app thiếu quyền/tùy contract |
| A05 | Required tenant absent | Deny |
| A06 | Required tenant present nhưng 0 values | Deny |
| A07 | Tenant value `""` | Deny |
| A08 | Tenant value chỉ whitespace | Deny |
| A09 | Tenant có 2 values khác nhau | Deny, không first-wins |
| A10 | Tenant có 2 values giống hệt nhau | Deny nếu exact cardinality 1 |
| A11 | Tenant 1 value nhưng không nằm allowlist | Deny |
| A12 | Group field missing/empty | Không cấp ROLE_REPORT_VIEWER |
| A13 | Group 2 values, approved value ở vị trí thứ hai | Vẫn có ROLE_REPORT_VIEWER |
| A14 | Group list có “Domain Admins” và approved group | Không cấp ROLE_ADMIN |
| A15 | Group list chỉ chứa unknown values | Không cấp app authorities ngoài defaults |
| A16 | Group values duplicate | Không làm tăng quyền, giới hạn input |
| A17 | Group có giá trị kiểu XML complex object | Deny/handling theo schema; không cast bừa |
| A18 | Group có 1000 values | Bounded input size/mapping policy |
| A19 | Group chứa leading/trailing whitespace | Chuẩn hóa chỉ theo contract; không substring role |
| A20 | Same `FriendlyName`, khác `Name` | Không nhầm hai attributes |
| A21 | Same `Name` nhưng `NameFormat` khác | Không gộp khi business contract không chấp nhận |
| A22 | Repeated `Attribute` blocks cùng Name | Xử lý duplicate/list theo policy, không bất ngờ overwrite |
| A23 | Email có 2 values khi field chỉ 0..1 | Không chọn ngẫu nhiên; có contract xử lý ambiguous email |
| A24 | NameID empty/missing | Deny identity link |
| A25 | NameID email mutable nhưng local ID dùng email | Test đổi email và tránh account collision |
| A26 | Attribute encrypted và missing ở bản plaintext sau decrypt | Kết quả mapping như field missing, không phải decrypt success là field đầy đủ |
| A27 | Local account disabled sau IdP SAML auth | Deny application access |
| A28 | Wrong tenant resource | Deny object/tenant access dù user có approved group |
| A29 | Session cũ còn role sau group revoked | Giới hạn cache/session/revalidation theo SLA |
| A30 | Multiple IdPs cùng `groups` name khác semantics | Map theo issuer/registration contract riêng |

## 19. Khác biệt Attribute.Value so với role string ngẫu nhiên

Các kiểu SAML `AttributeValue` có thể là `xs:string`, `xs:boolean`, `xs:integer` hoặc dữ liệu XML structured do extension định nghĩa. Khi Spring provider trả `Map<String,List<Object>>`:

- **Không ép `(String) list.get(0)`** mà chưa kiểm cardinality/type, vì `null`/non-string có thể ném exception.
- **Không `String.valueOf(object)` để tạo quyền**: Java Object/DOM `toString()` không là claim value an toàn.
- **Không tự động split dấu phẩy/semicolon** nếu contract không nói đó là một cách biểu diễn.
- **Không map `FriendlyName`** nếu IdP dùng URI claim name làm identifier chuẩn.
- **Không gộp attributes giữa hai Assertions** mà thiếu kiểm signature, subject equality, conditions và profile-specific semantics.
- **Không dùng “first assertion” hoặc “first attribute” mặc định** để xử lý những tình huống đa assertion hoặc duplicate attribute có nguy cơ nhầm dữ liệu; provider đã có validation policy, app cần thêm kiểm business.

Điều này đặc biệt quan trọng ở **multi-tenant SSO**: nếu tenant có hai values, một value là `reports` và value khác là `payments`, việc lấy value đầu và cấp role theo value thứ hai có thể tạo **authorization confusion**. Với identity-critical claim, yêu cầu **đúng một giá trị** là lựa chọn bảo thủ.

## 20. Xác thực đúng rồi mới làm data mapping

Một bài kiểm thử sai phổ biến:

~~~text
Input: raw base64 SAMLResponse
Test helper: base64 decode -> XML parser -> find <Attribute Name="groups">
Test: groups contains admin => login success
~~~

Đây **không phải** SAML2 security test, vì nó bỏ qua signature, trust anchors, decryption, XML signature reference protections, audience, replay, timestamps và recipient.

Cách đúng:

~~~text
Real signed/encrypted test response
  -> Spring SAML filter + OpenSAML provider validation
  -> authenticated principal + verified attribute Map
  -> role mapper tests
  -> application requestMatchers/tenant policy
~~~

Nếu test chỉ muốn mapping logic, **không cần SAML XML**; hãy unit-test như phần Java 17, ghi rõ “input đã được giả định là authenticated”. Nếu test muốn crypto, **đừng mock provider bằng true**; cần đi qua provider thật.

### XML Signature Wrapping và XML parser

SAML có lịch sử những lỗi **XML Signature Wrapping (XSW)** khi ứng dụng tự tìm Attribute/Assertion trong DOM khác với phần đã được chữ ký bảo vệ. OpenSAML xử lý các chi tiết signature references theo cấu hình/protocol. Tránh viết XPath “lấy Assertion đầu tiên ở bất cứ đâu” trên XML request. Tạo test negative có duplicate IDs/extra unsigned Assertion và xác nhận framework từ chối hoặc không bao giờ chọn giá trị không được signed/validated.

**Không bật XXE/DTD/external entity resolution** để parse SAML XML. Giới hạn request body size, XML nesting và number of elements; dùng library được bảo trì và cập nhật security patches.

## 21. Logs, PII và quản lý test fixtures

Assertion sau decrypt có thể mang email, employee ID, groups, NameID, tenant và dữ liệu nhạy cảm. Dù ở staging:

- Không log `SAMLResponse` Base64 hoặc decoded XML vào application logs, WAF, APM, HAR, CI artifacts hoặc bug tracker công khai.
- Không in private key hoặc full PEM vào test report.
- Dùng identities giả và certificates/keys **riêng lab**; không dùng IdP production key.
- Log event code như `SAML_DECRYPTION_FAILED`, `ATTR_REQUIRED_MISSING` và `APP_ROLE_DENIED`.
- Nếu cần correlation, dùng **ID ngẫu nhiên độc lập**, không lấy raw AssertionID/NameID hay token làm correlation key khi không có lý do.
- Hạn chế quyền đọc heap dumps, exception attachments, network traces, backups.
- Khi key mismatch, xác minh **fingerprint/cert metadata** qua kênh quản trị thay vì paste private key vào chat.
- Retention cho logs/fixtures tối thiểu; có script làm sạch test environment sau chạy.

**Không dựa vào XML Encryption để bảo vệ mọi log:** sau khi decrypt, Spring có plaintext assertion trong memory; một debug statement vô tình in ra toàn bộ dữ liệu nhạy cảm.

## 22. Runbook khi test thất bại

| Triệu chứng | Nguyên nhân ưu tiên | Điều không nên làm |
| --- | --- | --- |
| `EncryptedAssertion` không decrypt | Wrong private key/cert, key rotation, algorithm mismatch | Không disable encryption/signature validation |
| Thỉnh thoảng login fail theo pod | Key/cert secrets drift giữa replicas | Không dùng một key “dự phòng” chia mọi tenant |
| Plaintext test PASS, encrypted test FAIL | SP không có decryption credential/algorithm interop | Không kết luận Attribute mapper sai |
| EncryptedAssertion PASS, EncryptedAttribute FAIL | Assertion decrypter/key config khác | Không parse encrypted field như plaintext |
| Signed Assertion verification fail sau custom decryption | Sai thứ tự decrypt/verify, XML mutation | Không sửa signature bytes hoặc bỏ check |
| SAMLResponse signature FAIL | IdP verification cert/issuer/key rollover | Không tin mọi certificate |
| Issuer/Audience/Recipient fail | Metadata/ACS/entity ID sai | Không bypass conditions |
| Assertion expired/NotBefore | Clock/time profile issues | Không mở skew vô hạn |
| SAML auth PASS, app thiếu tenant | IdP mapper/claim NameFormat/expected name | Không cấp default tenant |
| SAML auth PASS, groups list empty | IdP group mapper/filter hoặc user chưa có entitlement | Không đặt ROLE_ADMIN mặc định |
| Multi-valued group chỉ lấy value đầu | Dùng `getFirstAttribute` sai contract | Đọc list, allowlist exact values |
| Optional email missing gây NPE | Code assumption email always present | Optional fallback và null-safety |
| Different type object causes ClassCastException | Mapper ép String mà không type check | Type validation và safe error |
| FriendlyName đúng nhưng Name sai | Mapping trông UI đúng nhưng claim identifier khác | Sửa hợp đồng Name/NameFormat |
| User thấy dữ liệu tenant khác | Tenant cardinality/mapping confusion | Fail closed + incident review |
| Một test chỉnh XML thất bại signature trước mapper | Fixture không được ký/mã hóa lại | Tạo fixture mới tại IdP hoặc test signer lab |
| Lộ decrypted Assertion trong log | Debug formatter/HTTP body capture | Disable capture, revoke/purge theo policy |

**Thứ tự chẩn đoán:** (1) registration/ACS/issuer; (2) signing trust; (3) decrypt key/algorithm; (4) assertion validation; (5) name/attribute extraction; (6) business mapping; (7) local authorization. Không dùng lỗi “user không có quyền” để biện minh cho việc thay decryption key.

## 23. Các bài tình huống thực hành

### Tình huống A — SAML không mã hóa hoạt động, bật encrypt thì fail

Đội IdP bật `EncryptedAssertion`. Spring có certificate public của IdP để verify signature, nhưng chưa có **SP private decryption key**.

**Kết luận:** cấu hình IdP verification certificate **không phải** decryption credential. Cần cung cấp đúng `Saml2X509Credential.decryption(privateKey, cert)` thuộc SP và đảm bảo IdP encrypt bằng public cert tương ứng, rồi test E2E. Không tắt encrypt hoặc signature chỉ để login lại.

### Tình huống B — thiếu email nhưng NameID ổn định

IdP bỏ `email` vì dữ liệu chưa được xác minh. SAML và tenant/group đều hợp lệ, ứng dụng không cần email cho authorization.

**Kết luận:** nên cho authentication/role mapping tiếp tục nếu email **optional** theo contract; UI có fallback. Không coi mọi missing attribute là security incident, và không tự đặt `email="admin@example"`.

### Tình huống C — hai giá trị tenant

IdP phát `tenant=["reports","payroll"]` nhưng ứng dụng expect exactly one. Code cũ gọi `getFirstAttribute` và cấp role dựa vào group Payroll.

**Kết luận:** **deny** vì ambiguous tenant. Đừng chọn first và cũng đừng tự union hai tenants, nhất là khi tenant là security boundary.

### Tình huống D — nhóm đa trị và Domain Admins

IdP gửi `groups=["Domain Admins","APP_REPORT_VIEWERS"]`. Ứng dụng Reports chỉ tin mapped group `APP_REPORT_VIEWERS`.

**Kết luận:** chỉ cấp `ROLE_REPORT_VIEWER`; `Domain Admins` không phải role ứng dụng. Nếu `getFirstAttribute("groups")` trả "Domain Admins", code business cần đổi để duyệt list; không rewrite group claim trên IdP để giữ may mắn thứ tự.

### Tình huống E — fixture “thiếu groups” nhưng test fail signature

Một kỹ sư copy raw SAML XML từ test và xóa `Attribute` group sau khi IdP đã ký.

**Kết luận:** signature fail là **đúng**; test **không đến được** business mapper. Cần regenerate/re-sign/re-encrypt bằng test IdP hoặc test riêng mapper từ verified attribute Map.

### Tình huống F — key rotation gây lỗi ngẫu nhiên

Pod A có private A+B, pod B chỉ A, IdP bắt đầu encrypt bằng B.

**Kết luận:** kiểm mount/secret rollout giữa replicas; giữ key overlap theo chính sách và metadata timing. Không ghi raw key vào log để so sánh; dùng fingerprint/cert ID có quản lý.

### Tình huống G — `EncryptedAttribute` không giải mã được, NameID vẫn hợp lệ

Response Assertion ký đúng và NameID đọc được, nhưng nhóm được mã hóa bằng cert/key không tương ứng.

**Kết luận:** không coi group vắng mặt và tự cấp default role. Provider decryption failure phải được xử lý đúng, **không cho authenticated session dựa trên dữ liệu incomplete** khi decryption failure là lỗi bảo mật.

## 24. Kế hoạch kiểm thử để bàn giao IdP/SP

**Bước 1 — Chốt business contract:** thuộc tính nào bắt buộc, 0..1 hay 0..N, Name/NameFormat, issuer, subject ID, group/role mapping, tenant, active status.

**Bước 2 — Chốt crypto contract:** Response hay Assertion ký, Assertion/Attribute/NameID có encrypt không, public/private cert nào, algorithm, metadata và rollover.

**Bước 3 — Dựng lab identities:** không dùng PII thật; tạo user bình thường, user nhiều nhóm, user thiếu optional, user wrong tenant, user disabled.

**Bước 4 — Sinh fixtures hợp lệ:** IdP test ký/mã hóa **sau khi** đã thay mapper fields; không sửa signed XML trực tiếp.

**Bước 5 — Kiểm Spring provider:** positive encrypted login, wrong key/signature, wrong audience, timeout/replay, encrypted attribute/ID.

**Bước 6 — Kiểm mapper:** missing/empty/multi-valued/type/cardinality; không role escalation; stable identity-link.

**Bước 7 — Kiểm authorization:** authenticated but missing app group → 403/deny theo thiết kế; tenant mismatch → deny.

**Bước 8 — Kiểm vận hành:** key rotation, multi-node, logging/privacy, metrics và alerting; không gửi key/XML thật lên ticket.

**Bước 9 — Kiểm cross-version:** resolved Spring Security 6/7, OpenSAML 4/5, IdP XML encryption algorithms; compile/run integration tests.

**Bước 10 — Ghi bằng chứng:** test ID, fixture class, expected stage, result, correlation ID (không secret), provider version, key certificate IDs/fingerprints phù hợp.

Không tuyên bố “SAML encryption passed” chỉ vì có `EncryptedAssertion` trong XML; **phải chứng minh Spring decrypt, verify và áp local policy đúng**.

## 25. Checklist cuối bài

- [ ] Phân biệt `EncryptedAssertion`, `EncryptedAttribute` và `EncryptedID`.
- [ ] Biết IdP encrypt bằng **SP public key**, SP decrypt bằng **private key**.
- [ ] Phân biệt SP decryption private key với IdP signing public certificate.
- [ ] Spring có `RelyingPartyRegistration` và decryption `Saml2X509Credential` đúng.
- [ ] Signature, issuer, destination, audience, recipient, time và replay không bị bypass.
- [ ] Test decryption success và wrong-key failure trên provider thực.
- [ ] Signed/encrypted fixtures được tạo **sau** khi IdP test mapper thay attributes.
- [ ] Không xóa XML đã ký rồi gọi đó là “test thiếu thuộc tính”.
- [ ] Required/optional claims có contract rõ và cardinality test.
- [ ] Missing, empty list, blank, wrong type và duplicate đều được test.
- [ ] Email/displayName optional không gây NPE hoặc account collision.
- [ ] Subject/NameID/tenant identity-critical không tự mặc định/first-wins.
- [ ] `AttributeValue` được xử lý là 0..N, không chắc là String.
- [ ] Multi-valued groups được duyệt đầy đủ, mapping theo allowlist.
- [ ] Không map `Domain Admins` thành `ROLE_ADMIN` của ứng dụng.
- [ ] `Name`/`NameFormat` được dùng theo hợp đồng, không tin `FriendlyName` tùy tiện.
- [ ] Không gộp giá trị từ nhiều Assertions chưa được kiểm đủ.
- [ ] Spring Security 6/7 và OpenSAML provider/credential API được kiểm đúng version.
- [ ] Có test local account disabled, tenant/object authorization và session lifecycle.
- [ ] XSW/XXE/oversized XML/replay negatives được kiểm.
- [ ] Có quy trình overlap và rollback khi rotate encryption certificate.
- [ ] Tất cả SP pods dùng cùng keysets theo policy; tenant keys không bị trộn.
- [ ] Không log `SAMLResponse`, decoded Assertion, NameID/PII, private keys.
- [ ] Có metrics/error codes phân biệt crypto failure và mapping/authorization failure.
- [ ] Unit, provider integration, E2E browser/IdP tests đều được thực hiện.

## 26. Tài liệu chính thức tham khảo

1. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP flow, OpenSAML, RelyingPartyRegistration và decryption credentials.
2. [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): OpenSaml5AuthenticationProvider, response/assertion decrypters, attributes, authorities và validation.
3. [Spring Security — SAML2 Migrations](https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html): Spring Security 7 chuyển sang `Saml2AssertionAuthentication`/`Saml2ResponseAssertionAccessor`.
4. [Spring Security — Saml2ResponseAssertionAccessor Javadoc](https://docs.spring.io/spring-security/site/docs/7.0.x/api/org/springframework/security/saml2/provider/service/authentication/Saml2ResponseAssertionAccessor.html): `getAttributes()` và `getAttribute(String)`.
5. [Spring Security — Saml2AuthenticatedPrincipal Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): API cũ/deprecated ở 7.x, `getFirstAttribute` và list values.
6. [Spring Security — Saml2X509Credential Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html): signature verification, signing, decryption credentials.
7. [OASIS SAML 2.0 Core — Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `EncryptedAssertion`, `EncryptedAttribute`, `Attribute`/`AttributeValue` cardinality, types và semantics.
8. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO/SubjectConfirmation và SP obligations.
9. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): SP entity ID/ACS, KeyDescriptor signing/encryption.
10. [W3C — XML Encryption Syntax and Processing 1.1](https://www.w3.org/TR/xmlenc-core1/): XML encryption representation và algorithm considerations.
11. [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): XML Signature, XSW, replay và SP validation.
12. [OWASP — XML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_Security_Cheat_Sheet.html): secure XML parsing, XXE và resource limits.
13. [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): integration tests cho security filters/authorization.
14. [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): tránh cache thông tin nhạy cảm sau SAML login.

**Tóm tắt:** Kiểm thử SAML2 cần chứng minh **decrypt đúng bằng private key của SP**, **verify signatures/protocol conditions đầy đủ**, rồi mới áp **hợp đồng thuộc tính và quyền**. `AttributeValue` có thể không có, có một hoặc nhiều giá trị; **thiếu email tùy chọn khác với thiếu tenant bắt buộc**, còn nhóm đa trị phải được xử lý bằng allowlist và không tạo quyền admin từ một giá trị bất kỳ. Spring Security 6 và 7 khác API đọc assertion; ứng dụng phải kiểm version thực và test ở cả **provider crypto path** lẫn **local mapping/authorization path**, tránh “PASS giả” do mock validation hoặc XML đã bị chỉnh làm hỏng chữ ký.