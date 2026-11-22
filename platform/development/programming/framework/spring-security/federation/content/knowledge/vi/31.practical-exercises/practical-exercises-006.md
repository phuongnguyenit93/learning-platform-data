# Luân chuyển chứng thư IdP và Service Provider mà vẫn duy trì đăng nhập

> **Module:** Spring Security – federation. **Chủ đề cha:** Thực hành tổng hợp. Bài thực hành xử lý một vòng đời luân chuyển khóa/chứng thư của **SAML 2.0 Identity Provider (IdP/Asserting Party)** và **Service Provider (SP/Relying Party)** với ứng dụng Spring Security. Mục tiêu là chuẩn bị tin cậy mới **trước** khi đổi key đang phát thông điệp, hỗ trợ overlap OLD+NEW, giữ các giao dịch đang chuyển tiếp và kiểm tra đăng nhập/đăng xuất liên kết thật, không nới lỏng validation. Ví dụ sử dụng **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x** trên Servlet stack. URL, entityID, alias và certificate path trong bài là dữ liệu sandbox; không dùng private keys của production.

## 1. Mục tiêu và nguyên tắc phạm vi

Sau bài học, bạn cần:

1. Phân biệt **IdP signing certificate**, **SP signing certificate**, **SP encryption/decryption certificate**, **metadata-signing certificate** và **TLS HTTPS certificate**; biết ai giữ private key và ai cần public certificate.
2. Thiết kế năm giai đoạn **baseline → pretrust/prepublish → activate → stabilize → retire** cho từng hướng key rollover.
3. Bảo đảm **IdP đổi signer** thì SP đã trust NEW; **SP đổi signer** thì IdP đã trust NEW; **SP đổi encryption cert** thì mọi SP instances đã có private decrypt NEW trước khi IdP encrypt NEW.
4. Kiểm `EntityDescriptor/@entityID`, `KeyDescriptor use=signing/encryption`, `AssertionConsumerService` (ACS), `SingleLogoutService` (SLO), `SingleSignOnService` (SSO), bindings, `AuthnRequestsSigned` và actual signer.
5. Cấu hình Spring Security `RelyingPartyRegistration`, `assertingparty.verification.credentials`, `signing.credentials` và `decryption.credentials`; hiểu khác nhau giữa metadata mới trên URL và runtime repository đã reload.
6. Phân biệt luân chuyển **X.509 certificate sử dụng cùng public/private key** và luân chuyển **keypair thật**; không mặc định thay Subject/NotAfter nghĩa là verifier đã sẵn sàng.
7. Kiểm SAML signature, Issuer, Audience, Recipient, Destination, InResponseTo, RelayState, NameID, SessionIndex, SLO, time/replay và encrypted Assertions trong overlap.
8. Chạy Java 17 `SamlRolloverPlanner.java` mô phỏng các release gates với stdout xác định, hiểu rõ mô hình không thay XML Signature validation thực.
9. Dựng IdP sandbox có ký được messages bằng OLD và NEW, thực hiện positive/negative tests cho mọi node, tenant, browser và ký/giải mã.
10. Chuẩn bị canary, monitoring, rollback và emergency key compromise response; không đánh đổi bảo mật lấy một dòng “zero downtime”.

**Đầu vào:** SAML 2.0 Web Browser SSO, SP–IdP metadata, AuthnRequest/Response/Assertion, LogoutRequest/Response, HTTP POST/Redirect binding, XML Signature/Encryption, X.509, Spring Security Servlet session, Java 17, Kubernetes/secret management.

**Định nghĩa “duy trì đăng nhập”:** giao dịch SSO/SLO hợp lệ trước/trong/sau rotation vẫn được kiểm chứng khi chính sách cho phép, các phiên HTTP đang tồn tại không bị phá chỉ vì deploy trust mới, và rollback khả thi trong cửa sổ được phê duyệt. Điều đó **không** buộc chấp nhận key đã compromise, assertion hết hạn, user bị disable, hoặc cho mọi thiết bị luôn đăng nhập.

## 2. Bản đồ vai trò khóa trong liên kết SAML

~~~text
               IdP: https://idp.test.example.org/saml
                 owns PRIVATE IDP-SIGNING KEY
                            |
     signs SAMLResponse/Assertion/LogoutRequest/LogoutResponse
                            v
                      Browser roundtrip
                            |
                            v
               Spring SP: urn:portal:prod:sp
               verifies using IDP PUBLIC cert(s)

 Spring SP owns PRIVATE SP-SIGNING KEY
           |
           +-- signs AuthnRequest/LogoutRequest/LogoutResponse -->
               IdP verifies using SP PUBLIC cert(s)

 IdP encrypts Assertion using SP PUBLIC ENCRYPTION certificate
           |
           v
 Spring SP decrypts using SP PRIVATE DECRYPTION key
~~~

| Secret/certificate | Private key thuộc | Public cert cần ở | Chiều cần test |
| --- | --- | --- | --- |
| IdP SAML signing | IdP | SP verification trust list | IdP-signed Response/Assertion, SLO messages → SP |
| SP SAML signing | SP | IdP SP-verification trust list | SP-signed AuthnRequest/LogoutRequest/LogoutResponse → IdP |
| SP SAML encryption | SP | IdP encryption config / SP metadata | IdP encrypts Assertion/NameID → SP decrypt |
| Metadata signing | Metadata publisher | Consumer metadata trust store | Trusted import/refresh of metadata |
| HTTPS/TLS server certificate | Ingress/Web server | Browser/JVM PKI trust | HTTPS transport/hostname, không thay SAML signer |

**Không nhập làm một:** Chứng thư TLS cho `portal.test.example.org` không mặc định có vai trò ký AuthnRequest; chứng thư IdP SAML signing có thể khác TLS certificate `idp.test.example.org`. Một keypair có thể phục vụ cả signing và decryption theo thiết kế IdP/SP, nhưng các thao tác rollover vẫn phải được test theo **hai hướng độc lập**.

**Không đồng nhất certificate và keypair:** Có thể cấp X.509 certificate mới chứa **cùng public key** hoặc tạo cặp khóa mới. Provider có thể pin exact certificate fingerprint thay vì public key, nên cả “renew cert same key” vẫn cần test/trust update. Đối với key compromise, **phải rotate keypair**, không chỉ đổi certificate chứa cùng compromised public key.

## 3. Quy tắc thứ tự: receiver ready trước producer switch

**IdP signer:** SP cần trust IDP-NEW public cert **trước khi** IdP ký bằng IDP-NEW.

**SP signer:** IdP cần trust SP-NEW public cert **trước khi** SP ký bằng SP-NEW.

**SP encryption:** SP cần cài matching private ENC-NEW và test decrypt **trước khi** IdP encrypt bằng SP ENC-NEW public cert. SP giữ ENC-OLD private key khi encrypted Assertions cũ vẫn có thể quay về.

~~~text
T0 BASELINE
  Producer uses OLD
  Receiver trusts/can-decrypt OLD

T1 PREPARE
  NEW keypair generated, secrets isolated, metadata approved
  Receiver trusts/can-decrypt OLD + NEW
  Producer still uses OLD

T2 ACTIVATE
  Producer switches to NEW
  Receiver still accepts OLD + NEW

T3 OBSERVE
  Test every IdP tenant, SP node, browser and SSO/SLO binding
  Keep OLD where in-flight messages/rollback require it

T4 RETIRE
  OLD no longer produced, no outstanding OLD messages
  Receiver removes OLD according to security policy
  Old secret revoked/removed after approval
~~~

**Không dựa vào thời gian cố định** như “sau 24 giờ xóa OLD”. Cửa sổ overlap cần tính metadata cache TTL, replication của IdP, thời gian SAML Response/LogoutResponse qua browser, MaxAge/clock skew, session/request repository TTL, secret propagation tới nodes, ability to rollback và tuổi chứng thư.

**Một ngộ nhận thường gặp:** “Metadata có NEW cert” **không** tương đương “IdP đang ký bằng NEW”, “SP đã reload và trust NEW” hoặc “trên mọi region đều sẵn sàng”. Bằng chứng phải là effective trust set và actual signature verification.

## 4. Baseline cho một SP–IdP registration

Fixture sandbox:

~~~text
registrationId          = corporate
SP entityID             = urn:portal:prod:sp
SP ACS                  = https://portal.test.example.org/login/saml2/sso/corporate
SP SLO                  = https://portal.test.example.org/logout/saml2/slo
IdP entityID            = https://idp.test.example.org/saml
IdP SSO                 = https://idp.test.example.org/sso
IdP SLO                 = https://idp.test.example.org/slo
IdP active signer       = IDP-OLD
IdP candidate signer    = IDP-NEW
SP active signer        = SP-OLD
SP candidate signer     = SP-NEW
SP decrypt OLD/NEW      = ENC-OLD / ENC-NEW
Signing verification    = exact SHA-256 fingerprints
Response binding        = HTTP-POST
AuthnRequest binding    = HTTP-Redirect (IdP policy)
SLO binding             = verify actual IdP metadata
Deployment              = 3 Spring Pods behind HTTPS ingress
Registration source     = in-memory/static at boot or refreshable repository
Session store           = shared or in-memory, document effective behavior
~~~

Mỗi entry phải có **issuer/entityID**, fingerprint, effective signing algorithm, NotBefore/NotAfter, current active status, tenant, trust metadata provenance, owner, target date và test artifact ID. Không ghi private keys, raw SAMLRequest/SAMLResponse, session cookie, NameID thật hay tokens trong workbook/incident ticket.

### 4.1. Kiểm kê nguồn tin

| Nguồn | Nội dung lấy | Không lấy |
| --- | --- | --- |
| IdP approved metadata | IdP issuer, SSO/SLO URLs, signing public certs, validUntil/cacheDuration | IdP private key |
| SP approved metadata | SP entityID, ACS/SLO URLs, public sign/encrypt certs | SP private keys |
| IdP admin registration | SP active/secondary trusted signers, encryption selection policy | Admin password |
| Spring effective RPR | Approved issuer, verifier fingerprints, SP signer/decrypt cert aliases | Raw credentials |
| Secrets manager | Secret version/alias, policy, mount path/permissions | Secret values đưa vào logs |
| Browser + SP/IdP tests | Signed-by-OLD/NEW outcomes, correlation, Session continuity | Raw bearer headers/cookies |
| Platform config | Nginx scheme/host, shared session store, replica versions | Access to unrelated tenant secrets |

**Metadata signatures:** Nếu tổ chức dùng signed federation metadata, phải kiểm metadata signer/trust anchor **riêng**. Một cert mới bên trong metadata chưa được xác thực **không** tự biến thành cert đáng tin chỉ vì nó xuất hiện trong XML. Nếu tải qua HTTPS, vẫn phải kiểm approved URL/entityID và metadata trust policy.

### 4.2. Những thuộc tính phải cố định khi chỉ rotate cert

- SP `EntityDescriptor/@entityID` và IdP `EntityDescriptor/@entityID`, không tự đổi logical identity khi Subject CN thay.
- IdP `SingleSignOnService.Location/Binding` và `SingleLogoutService.Location/Binding` nếu không chủ động migration endpoint.
- SP `AssertionConsumerService.Location/Binding/index/isDefault` và `SingleLogoutService.Location`; public HTTPS host/port/path phải đúng.
- `AuthnRequestsSigned`, `WantAssertionsSigned` và actual signature requirements.
- `NameIDFormat`, AttributeStatements/groups, `AuthnContextClassRef` và role mapping.
- Request correlation `InResponseTo`/`RelayState`, time/replay checks, session handling.
- IdP identity resolver theo registrationId/tenant; không trộn keys giữa IdP A và IdP B.

Khi chỉ thay key, phải review mọi khác biệt khác trong metadata như **drift**, không lặng lẽ bỏ Validation vì MetadataGenerator mới khác cấu trúc.

## 5. Quy trình IdP signing certificate rotation

### 5.1. Publish NEW nhưng giữ OLD active

1. IAM tạo IDP-NEW keypair bằng HSM/secret store approved, kèm public certificate đáp ứng crypto policy.
2. Kiểm SHA-256 fingerprint/NotBefore/NotAfter, key algorithm, signer alias/region và approval.
3. Công bố IDP-NEW **public signing certificate** trong IdP metadata/approved distribution, nếu provider hỗ trợ dual certificates; giữ IDP-OLD trong trust overlap.
4. **IdP tiếp tục ký bằng IDP-OLD** trong thời gian các SP cập nhật trust.
5. SP owner ingest IDP-NEW vào **đúng RelyingPartyRegistration** của issuer đã đăng ký; không trust cert này cho mọi IdPs hoặc mọi tenants.
6. Mỗi SP node báo effective verifier set gồm OLD+NEW và có test SSO/SLO signed-by-OLD+NEW.
7. Chỉ khi tất cả SP nodes/tenants ready, IAM mới activate NEW signer ở IdP.

Metadata IdP minh họa (lược bytes):

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.test.example.org/saml">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <!-- Public X.509 certificate IDP-OLD -->
    </md:KeyDescriptor>
    <md:KeyDescriptor use="signing">
      <!-- Public X.509 certificate IDP-NEW -->
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.test.example.org/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Đây là XML mô tả, không phải metadata hoàn chỉnh để import** vì chưa có `ds:KeyInfo`/`ds:X509Certificate` và metadata trust signature. Trong metadata thực, `KeyDescriptor` có thể lặp. **Thứ tự các certs không bảo đảm cert nào active**; provider có thể đặt “active/secondary” trong UI/API riêng.

### 5.2. Receiver SP pretrust

~~~text
Before:
 SP approved IDP verification = [IDP-OLD]

During overlap:
 SP approved IDP verification = [IDP-OLD, IDP-NEW]

After safe retirement:
 SP approved IDP verification = [IDP-NEW]
~~~

Spring Security verifier cần dùng đúng public keys từ IdP metadata hoặc approved static certificates. Không lấy `KeyInfo` của một SAMLResponse do browser cung cấp làm “cert mới” để verify chính nó. Một signed Response bằng IDP-NEW với Audience/Recipient sai vẫn phải reject dù signer được trust.

### 5.3. Active switch và observation

Khi IdP chuyển ký NEW:
- New AuthnRequests vẫn dùng approved SP issuer/ACS; IdP trả signed `SAMLResponse`/`Assertion`, SP verify IDP-NEW.
- Nếu IdP ký Response và Assertion bằng các key khác nhau trong rollout, SP cần verify từng signed element theo policy.
- IdP-initiated `LogoutRequest`/RP `LogoutResponse` phải được SP verify bằng approved IDP-NEW nếu IdP dùng signer mới cho SLO.
- Existing Spring authenticated HTTP sessions thường không tự bị invalidate do verification cert thay; **new login tests** mới chứng minh new signer chạy.
- Nếu IdP multi-region chưa đồng nhất, một region còn ký OLD; trust overlap bảo vệ continuity nhưng vẫn phải quan sát signer per region.

**Retire IDP-OLD** chỉ khi không còn issuer/nodes ký OLD, in-flight browser SAML posts/retries đã drain, metadata refresh và SP trust đã hội tụ, rollback không cần OLD và Security owner chấp thuận. Nếu OLD bị compromised, cần ưu tiên revocation/incident dù có gián đoạn.

## 6. SP signing certificate rotation

SP ký `AuthnRequest` nếu IdP yêu cầu, và signed SLO messages theo policy. Vì **IdP là verifier**, IdP phải nhận NEW public SP cert **trước khi** SP ký bằng NEW.

### 6.1. Kế hoạch

1. SP owner tạo SP-NEW private/public keypair, secure mount secret cho canary; lưu public fingerprint.
2. Public SP metadata hoặc IdP registration quảng bá SP-NEW (cùng SP-OLD nếu provider cho phép). IdP verify trust OLD+NEW trong overlap.
3. **SP vẫn active ký bằng SP-OLD** khi IdP đang load metadata/trust.
4. IdP sandbox kiểm signed AuthnRequest bằng SP-OLD/NEW; IdP production effective trust status xác nhận.
5. SP canary switch active signer sang SP-NEW và phát actual signed AuthnRequests. Kiểm signer fingerprint/IdP verify, Issuer/Destination/binding/RelayState đúng.
6. Kiểm signed LogoutRequest/LogoutResponse bằng NEW (nếu SLO dùng).
7. Roll out remaining SP nodes, keep OLD trust ở IdP cho đến khi traffic OLD chấm dứt/rollback window đóng; sau đó retire OLD.

| Pha | SP active signer | IdP trusted SP signers | Kết quả |
| --- | --- | --- | --- |
| Baseline | SP-OLD | SP-OLD | Ổn |
| Pretrust | SP-OLD | SP-OLD+SP-NEW | Không gián đoạn |
| Canary | Một số SP-NEW, số khác SP-OLD | SP-OLD+SP-NEW | Phải verify cả hai |
| Full switch | SP-NEW | SP-OLD+SP-NEW | Theo dõi OLD in-flight |
| Retire | SP-NEW | SP-NEW | Chỉ sau drain/approval |

**Không suy rằng thêm hai `signing.credentials` vào YAML tự động công bố một “primary vs secondary” policy hoặc chọn NEW để ký.** Kiểm actual signed AuthnRequest/LogoutRequest và SP metadata effective; có thể cần prepublish new cert qua approved IdP admin UI/metadata generator tùy version. Nếu IdP chỉ trust một signer, coordinated cutover/change window có thể cần thiết. Không hứa zero downtime nếu không có dual-key support.

### 6.2. SLO có thể hỏng dù SSO pass

Một IdP có thể không yêu cầu signed AuthnRequest nhưng lại yêu cầu signed LogoutRequest. Nếu SP signer đổi mà IdP chưa trust NEW, RP-initiated logout có thể dọn local session nhưng IdP SLO reject. IdP-initiated flow cũng có SP signed LogoutResponse cần IdP verify. Luôn test:

~~~text
SP -> IdP: AuthnRequest signed SP-NEW
SP -> IdP: LogoutRequest signed SP-NEW
SP -> IdP: LogoutResponse signed SP-NEW

IdP -> SP: SAMLResponse signed IDP-NEW
IdP -> SP: LogoutRequest signed IDP-NEW
IdP -> SP: LogoutResponse signed IDP-NEW
~~~

Đo actual binding và signature locations. Với HTTP-Redirect binding, chữ ký có thể ở `SigAlg`/`Signature` query fields; đừng chỉ tìm XML `ds:Signature` như trong HTTP-POST.

## 7. SP encryption/decryption rotation

Phía IdP dùng SP **public encryption certificate** để mã hóa Assertion/NameID; SP dùng matching **private decryption key**. Trình tự khác signer: **SP phải cài NEW private decrypt key trên mọi instances trước khi IdP dùng NEW public encrypt cert**.

~~~text
T0: IdP encrypts ENC-OLD
    SP decrypts ENC-OLD

T1: SP installs ENC-NEW private key
    SP decrypts ENC-OLD + ENC-NEW
    IdP still encrypts ENC-OLD

T2: SP publishes new public ENC-NEW cert
    IdP registers/selects ENC-NEW under approved policy
    SP remains able to decrypt OLD + NEW

T3: IdP encrypts ENC-NEW
    SP decrypts OLD + NEW

T4: All old encrypted messages drained
    SP retires ENC-OLD private key safely
~~~

### 7.1. Cẩn trọng khi publish encryption cert

Một số IdP có thể tự chọn first/last cert trong `KeyDescriptor use=encryption`, hoặc đổi ngay khi ingest metadata. Vì vậy **không publish NEW trước khi tất cả Pods có thể decrypt NEW**, trừ khi đã xác minh IdP không tự switch. Nếu IdP không hỗ trợ multiple encryption certs, cần **preinstall NEW private key** rồi coordinate một lần switch; overlap private keys ở SP vẫn giúp giảm rủi ro.

**Không xóa ENC-OLD ngay:** Một browser có thể giữ `SAMLResponse` chứa `EncryptedAssertion` tạo trước T3, POST callback đến sau T3. Nếu SP đã xóa private OLD, fail decrypt dù IdP đã chuyển encrypt NEW. Tương tự `EncryptedAttribute`/`EncryptedID` và một số SLO messages.

### 7.2. Test dual-decrypt thật

| Test | IdP encrypts for | SP available keys | Expected |
| --- | --- | --- | --- |
| E1 | ENC-OLD | ENC-OLD+ENC-NEW | Decrypt, sau đó validate signature/issuer/audience |
| E2 | ENC-NEW | ENC-OLD+ENC-NEW | Decrypt, validate |
| E3 | ENC-NEW | chỉ ENC-OLD | Reject, không plaintext fallback |
| E4 | ENC-OLD | chỉ ENC-NEW | Reject, mô phỏng retire quá sớm |
| E5 | Unknown public key | ENC-OLD+ENC-NEW | Reject |
| E6 | ENC-NEW nhưng Pod B chưa có key | A pass, B fail → rollout blocked |
| E7 | Encrypted NameID dùng OLD | OLD+NEW | Decrypt theo profile/policy |
| E8 | Signing key = encryption key pair | Đổi chung | Test hai hướng độc lập |

**Một Response chỉ được ký nhưng không được mã hóa không chứng minh decryption rotation thành công**. IdP sandbox phải tạo actual encrypted Assertion cho mỗi public key.

## 8. Spring Security: trust set, metadata và runtime

Spring Security biểu diễn quan hệ SP–IdP qua `RelyingPartyRegistration`. `assertingparty.verification.credentials` biểu diễn IdP public keys dùng verify; `signing.credentials` biểu diễn SP private/public signing keys; `decryption.credentials` chứa SP private/public decryption keys.

### 8.1. IdP dual verification trong Spring Boot YAML

Fragment cấu hình cho app Servlet (cần dependencies `spring-security-saml2-service-provider` và đúng IdP sandbox):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "urn:portal:prod:sp"
            assertion-consumer-service-location: >-
              https://portal.test.example.org/login/saml2/sso/corporate
            assertingparty:
              entity-id: "https://idp.test.example.org/saml"
              singlesignon:
                url: "https://idp.test.example.org/sso"
                sign-request: true
              verification:
                credentials:
                  - certificate-location: >-
                      file:/run/trust/saml/idp-signing-old.crt
                  - certificate-location: >-
                      file:/run/trust/saml/idp-signing-new.crt
            signing:
              credentials:
                - private-key-location: >-
                    file:/run/secrets/saml/sp-signing-active.key
                  certificate-location: >-
                    file:/run/secrets/saml/sp-signing-active.crt
~~~

- `verification.credentials[]` gồm hai **approved public IdP signers** cho cùng IdP entityID; không chứa IdP private key.
- `signing.credentials[]` là SP private + public signing key. Ví dụ chỉ khai một **active** SP signer, do thứ tự/chọn signer khi có nhiều credentials phụ thuộc implementation; đừng tự giả định YAML list quyết định policy publish vs activate.
- `entity-id` và ACS giữ đúng federation contract, không vô tình đổi do rotation.
- Nếu IdP cung cấp `assertingparty.metadata-uri`, phải xác định liệu app dùng **metadata import** hay static verification credentials làm source of truth; không giả định config tự merge ở mọi Boot version.
- Nếu đã tạo custom `RelyingPartyRegistrationRepository` bean, Boot auto configuration có thể không áp static YAML theo cách dự kiến; kiểm effective runtime registrations.
- `singlesignon.sign-request=true` là ví dụ IdP yêu cầu signed AuthnRequest, cần IdP trust SP signing cert. Không tùy tiện đổi để giảm lỗi.

### 8.2. SP dual decryption

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            decryption:
              credentials:
                - private-key-location: >-
                    file:/run/secrets/saml/sp-decryption-old.key
                  certificate-location: >-
                    file:/run/secrets/saml/sp-decryption-old.crt
                - private-key-location: >-
                    file:/run/secrets/saml/sp-decryption-new.key
                  certificate-location: >-
                    file:/run/secrets/saml/sp-decryption-new.crt
~~~

Spring/OpenSAML có thể dùng multiple registered `Saml2X509Credential` decryption credentials để giải encrypted SAML elements. **Phải test actual encrypted Response bằng cả public keys**, không chỉ assert application startup. Khi dùng YAML fragment này, giữ nguyên những cấu hình khác của registration trong file đầy đủ; không copy đè mất IdP issuer, SSO location, signing trust.

### 8.3. SP signing active OLD và NEW: hai phiên bản rollout

**Old active fragment:**

~~~yaml
signing:
  credentials:
    - private-key-location: file:/run/secrets/saml/sp-signing-old.key
      certificate-location: file:/run/secrets/saml/sp-signing-old.crt
~~~

**New active fragment:**

~~~yaml
signing:
  credentials:
    - private-key-location: file:/run/secrets/saml/sp-signing-new.key
      certificate-location: file:/run/secrets/saml/sp-signing-new.crt
~~~

Đây là fragments **dưới `registration.corporate`**, không phải toàn file. Khi switch sang NEW:
- IdP trusted verification set đã có SP-NEW.
- Kiểm SP metadata công bố public certs theo kế hoạch; nếu cần publish OLD+NEW nhưng framework chỉ công bố active credential theo cấu hình, phối hợp IdP upload/metadata publisher approved.
- Kiểm actual outbound signed `AuthnRequest`/`LogoutRequest` dùng NEW, không chỉ xem alias trong Secret.
- Đảm bảo Pods đã reload private key thay vì giữ key cũ trong application memory.
- Test idempotent config rollout, không mất `RelyingPartyRegistration` giữa restart.

### 8.4. Metadata URL thay đổi không tự reload Registration

Một `RelyingPartyRegistrations.fromMetadataLocation(...)` khi được gọi để xây `InMemoryRelyingPartyRegistrationRepository` thường lấy metadata tại thời điểm dựng registration. Sau đó IdP publish NEW trên web **không bảo đảm** mọi Spring Pods tự refresh.

Các lựa chọn có chủ đích:
1. **Static reload:** cập nhật approved local metadata/public certs rồi rolling restart; kiểm every Pod's effective trust.
2. **Refreshable repository/cache:** dùng API được hỗ trợ ở phiên bản Spring Security thực tế, quản lý cache TTL, refresh integrity, fallback known-good và alerts; có các phiên bản hỗ trợ `CachingRelyingPartyRegistrationRepository` qua supplier + cache.
3. **Managed config service:** publish updated registrations theo immutable/versioned snapshot sau approval; swap atomically, monitor.
4. **IdP metadata import by pipeline:** tải signed metadata từ approved endpoint, verify issuer/fingerprint, stage deployment và test before activation.

**Không tự fetch metadata từ arbitrary client URL, không trust-all TLS, không dùng cert từ response KeyInfo như dynamic trust anchor.** Nếu refresh fail, dùng known-good policy trong giới hạn đã phê duyệt hoặc fail closed; không trust unknown signer để “tạm duy trì”.

### 8.5. SecurityFilterChain cho sandbox

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain samlChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/error").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .saml2Metadata(Customizer.withDefaults())
        .saml2Logout(Customizer.withDefaults())
        .build();
}
~~~

Đây là **code fragment** cho một class `@Configuration` trong project Spring Boot có Spring SAML2 dependency, chứ không phải standalone Java app. SLO cần `SingleLogoutService` của IdP, SP signing credentials và supported bindings. Lưu ý thứ tự/endpoint/authentication policy khi app còn form/OIDC login; không coi có DSL là signed E2E pass.

## 9. Đối chiếu metadata và certificate fingerprints

Metadata IdP/SP thực có thể có nhiều `KeyDescriptor`; **không** so chỉ phần tử đầu tiên hoặc text Base64 với whitespace. Trích certificate DER, tính SHA-256 fingerprint, so signer roles và provenance.

### 9.1. Lệnh chỉ đọc public cert

~~~bash
# Public X.509 certificate, không in private key:
openssl x509 -in idp-old.crt -noout \
  -fingerprint -sha256 -dates -subject -issuer

openssl x509 -in idp-new.crt -noout \
  -fingerprint -sha256 -dates -subject -issuer

openssl x509 -in sp-signing-new.crt -noout \
  -fingerprint -sha256 -dates -subject -issuer
~~~

- SHA-256 fingerprint tính trên DER certificate, không phải trên chuỗi PEM nguyên văn. PEM line wrapping có thể khác dù cùng certificate.
- `NotBefore`/`NotAfter` giúp kiểm thời hạn và active time; cách framework kiểm expiry có thể phụ thuộc provider/policy. Không mặc định cert expired luôn được accept hoặc luôn reject.
- Public cert có thể self-signed trong SAML. PKIX `openssl verify` thất bại theo CA trust không tự chứng minh federation trust sai nếu mô hình là approved certificate pinning. Cần kiểm **actual SAML verifier** và chính sách.
- Kiểm public key algorithm/key size/signature digest phù hợp policy; không bật SHA-1/weak cipher chỉ để IdP accept.
- Không in private key bằng `cat`, `openssl pkey -text` hoặc copy `.p12`/`.key` ra Git, ticket, terminal được ghi log.

### 9.2. Các trường metadata cần review

| Trường | Vì sao |
| --- | --- |
| `EntityDescriptor/@entityID` | Cố định SP/IdP logical identity |
| `KeyDescriptor@use=signing` | Bên nhận có old+new approved public signing certs |
| `KeyDescriptor@use=encryption` | IdP biết cert để encrypt cho SP |
| `validUntil`/`cacheDuration` | Cache freshness và metadata expiry |
| `Metadata XML signature` | Provenance, tránh attacker thêm cert |
| `SingleSignOnService.Location/Binding` | AuthnRequest Destination, supported binding |
| `AssertionConsumerService.Location/Binding` | Response Recipient/Destination and browser POST |
| `SingleLogoutService.Location/Binding/ResponseLocation` | SLO signed requests/responses đúng bên |
| `AuthnRequestsSigned`/`WantAssertionsSigned` | Policy ký/verify không bị giảm |
| `NameIDFormat` | Identity mapping không trôi |
| X.509 NotBefore/NotAfter/fingerprint | Cert lifecycle |
| Multiple KeyDescriptors | Overlap, thuật toán/key use và behavior của provider |

**Certificate rollover không được âm thầm đổi `entityID` hoặc ACS**. Một IdP có thể pin signing certificate vào một SP entityID; certificate subject CN khác không cần đổi entityID. Những thay đổi Entity ID/endpoint phải là change request federation riêng.

## 10. Bảo toàn SAML validation trong lúc key rotation

Khi SP trust cả IDP-OLD và IDP-NEW, phạm vi trust được nới **theo public keys được phê duyệt**, không phải nới mọi trường SAML.

| Kiểm tra | Vẫn bắt buộc trong overlap |
| --- | --- |
| `Response.Issuer`, `Assertion.Issuer` | Đúng trusted IdP entityID/registration |
| XML signature | Đúng public signing cert OLD hoặc NEW được approve, không KeyInfo self-trust |
| `Assertion.AudienceRestriction` | Đúng SP entityID |
| `Response.Destination` | Đúng SP public ACS |
| `SubjectConfirmationData.Recipient` | Đúng SP public ACS |
| `InResponseTo`/`RelayState` | Khớp pending request khi SP-initiated |
| `Conditions.NotBefore/NotOnOrAfter` | Time/clock skew theo policy |
| `NameID`/`NameIDFormat` | Map user theo trusted IdP/tenant |
| `AuthnContextClassRef` | Assurance requirement không downgrade |
| `AuthnStatement.SessionIndex` | SLO đúng session nếu dùng |
| Replay cache/request ID | Không reuse signed Assertion |
| Encryption | Private decrypt keys OLD/NEW phù hợp key thực sự IdP dùng |

**Signed-by-NEW không cứu một Response sai Audience/Recipient.** Để test riêng Audience, IdP sandbox phải tạo rồi **ký lại** Response sai Audience bằng NEW private key. Nếu chỉ sửa XML sau signing thì nó fail vì chữ ký và chưa chứng minh Audience validator.

**Unsolicited/IdP-initiated SSO:** Có thể không có `InResponseTo` theo profile nếu IdP tự bắt đầu flow; phải test theo explicit policy. Không bỏ correlation cho mọi SP-initiated flows chỉ vì một IdP không có request state.

**Metadata signing vs message signing:** Nếu metadata được ký bởi certificate M, signed Assertion bằng certificate A, thì luân chuyển A không mặc nhiên cập nhật M. Metadata refresh phải xác minh đúng metadata trust anchor; không lấy public key A từ metadata **chưa được verify** để tự bootstrap metadata trust.

## 11. Key rotation và tính liên tục của phiên người dùng

Một HTTP session đã authenticated thường lưu Spring `SecurityContext`/`Authentication`; server **không nhận lại SAMLResponse ở mỗi HTTP request**. Do đó IdP signer rollover thông thường **không tự logout phiên hiện hữu**. Tuy nhiên redeploy/restart có thể mất HTTP session **nếu ứng dụng dùng in-memory session store**.

Test phải tách:
1. **Existing session continuity:** user QA login bằng IDP-OLD, giữ session fingerprint đã ẩn danh; deploy dual trust, `GET /private` vẫn authorized nếu session store policy cho phép.
2. **New login with OLD signer:** test IdP sandbox ký OLD trong overlap, xác minh.
3. **New login with NEW signer:** test sandbox ký NEW, xác minh.
4. **In-flight AuthnRequest:** request ID được tạo khi OLD active, Response ký NEW sau activation; verifier mới và request repository phải còn correlation.
5. **Logout:** RP/IdP-initiated LogoutRequest/Response signed đúng, local session cleanup vẫn hoạt động.
6. **Multi-node:** request phát từ Pod A, callback tới Pod B; shared state/affinity và trust sets đúng.
7. **SameSite cookie:** browser cross-site SAML HTTP-POST có thể không gửi session cookie với `SameSite=Lax`; kiểm `SameSite=None; Secure` khi profile cần cùng CSRF cho các endpoints khác.
8. **Authorization:** user có SAML Authentication hợp lệ nhưng thiếu role có thể đúng là 403, không nên sửa cert.

### 11.1. Ví dụ in-flight khi IdP signer đổi

~~~text
09:00:00 SP creates AuthnRequest ID _req-17
         Stores pending request in approved repository
09:00:02 IdP activates IDP-NEW signer
09:00:03 Browser posts signed SAMLResponse using IDP-NEW
         InResponseTo = _req-17

SP must:
  - trust IDP-NEW for expected IdP entityID
  - find pending _req-17 in same user/session context
  - check signature, issuer, audience, destination, recipient, time
  - enforce replay protection
  - authenticate if user account/policy is allowed
~~~

Nếu nhận 400 do `InResponseTo` hoặc cookie missing, đó là **state/repository issue**, không mặc định signer NEW sai. Debug theo step bằng redacted logs, không bỏ InResponseTo để “fix”.

## 12. Nhiều SPs, nhiều IdPs, nhiều Pods

Trong tổ chức có 20 SPs dùng một IdP, mỗi SP có nhịp cập nhật trust riêng. IdP **không được switch NEW** trước khi những SP bắt buộc đã ready, trừ khi có verified fallback/partial impact plan. Một vài IdPs hỗ trợ per-application signer, số khác dùng tenant/global signer; không mặc định mọi provider có cùng capability.

Với một Spring ứng dụng đa IdP:
- Mỗi `registrationId` được gắn đúng IdP issuer/verification certs; NEW cert của IdP A không được dùng cho B.
- Một `NameID` giống nhau từ A/B không chứng minh cùng người dùng; user mapping phải dùng issuer/tenant binding.
- Mỗi IdP có thể rotate vào ngày khác nhau, không cập nhật một global trust store không phân biệt entity.
- Một SP shared signing key dùng bởi nhiều IdPs cần bảo đảm **tất cả relying parties** sẵn sàng verify SP-NEW trước switch toàn cục; hoặc tách per-IdP signing credentials nếu kiến trúc hỗ trợ.
- Các Pods phải cùng effective verifier/decrypt keys theo vòng đời, dù signer active có thể rollout canary OLD/NEW khi IdP trust cả hai.
- Một Pod chưa nhận new key tạo intermittent login failures theo LB; cần report metric per instance, không chỉ overall success rate.
- TLS ingress/metadata endpoints nên giữ canonical HTTPS scheme/host, không phát sinh `http://pod:8080` và không accept untrusted `X-Forwarded-Host`.

**Cluster request state:** SAML AuthnRequest/LogoutRequest repositories có TTL; rolling deployment với in-memory session và không có sticky policy có thể gây mất correlation dù cert đủ. Không sửa bằng bypass InResponseTo/replay.

## 13. Java 17 standalone: SamlRolloverPlanner

Chương trình mô phỏng **release gate**: receiver phải ready NEW trước producer switch; OLD chỉ retire khi không còn in-flight. Nó **không kiểm XML Signature, không parse metadata, không xử lý SAML tokens**, không được dùng làm production authenticator. Các booleans là bằng chứng QA có kiểm chứng, không phải dữ liệu từ browser.

**Tệp `SamlRolloverPlanner.java`:**

~~~java
public class SamlRolloverPlanner {
    enum Direction {
        IDP_SIGNING, SP_SIGNING, SP_ENCRYPTION
    }

    record State(
        boolean oldAvailable,
        boolean newAvailable,
        boolean newAdvertised,
        boolean producerUsesNew,
        boolean oldInFlight,
        boolean probesPass) {}

    static String decide(Direction direction, State s) {
        if (direction == Direction.IDP_SIGNING) {
            if (s.producerUsesNew() && !s.newAvailable()) {
                return "BLOCK_IDP_NEW_UNTRUSTED";
            }
            if (!s.producerUsesNew() && !s.oldAvailable()) {
                return "BLOCK_IDP_OLD_UNTRUSTED";
            }
            if (s.oldInFlight() && !s.oldAvailable()) {
                return "BLOCK_OLD_MESSAGE_IN_FLIGHT";
            }
            if (!s.probesPass()) {
                return "HOLD_CANARY";
            }
            return s.producerUsesNew()
                ? (s.oldAvailable()
                    ? "IDP_NEW_ACCEPTED_KEEP_OLD"
                    : "IDP_NEW_ACCEPTED_CAN_RETIRE_OLD")
                : "IDP_OLD_ACCEPTED";
        }

        if (direction == Direction.SP_SIGNING) {
            if (s.producerUsesNew() && !s.newAdvertised()) {
                return "BLOCK_SP_NEW_UNADVERTISED";
            }
            if (s.producerUsesNew() && !s.newAvailable()) {
                return "BLOCK_SP_IDP_NOT_READY";
            }
            if (!s.producerUsesNew() && !s.oldAvailable()) {
                return "BLOCK_SP_IDP_OLD_UNTRUSTED";
            }
            if (!s.probesPass()) {
                return "HOLD_CANARY";
            }
            return s.producerUsesNew()
                ? "SP_NEW_SIGNING_ACCEPTED"
                : "SP_OLD_SIGNING_ACCEPTED";
        }

        // SP_ENCRYPTION: available means SP holds matching private key.
        if (s.oldInFlight() && !s.oldAvailable()) {
            return "BLOCK_INFLIGHT_OLD_DECRYPTION";
        }
        if (s.producerUsesNew() && !s.newAdvertised()) {
            return "BLOCK_NEW_ENCRYPTION_NOT_PUBLISHED";
        }
        if (s.producerUsesNew() && !s.newAvailable()) {
            return "BLOCK_NEW_DECRYPTION_KEY_UNAVAILABLE";
        }
        if (!s.producerUsesNew() && !s.oldAvailable()) {
            return "BLOCK_OLD_DECRYPTION_KEY_UNAVAILABLE";
        }
        if (!s.probesPass()) {
            return "HOLD_CANARY";
        }
        return s.producerUsesNew()
            ? "SP_NEW_ENCRYPTION_ACTIVE"
            : "SP_OLD_ENCRYPTION_ACTIVE";
    }

    static void show(String label, Direction d, State s) {
        System.out.println(label + "=" + decide(d, s));
    }

    public static void main(String[] args) {
        show("idpBaseline", Direction.IDP_SIGNING,
            new State(true, false, false, false, false, true));
        show("idpPretrust", Direction.IDP_SIGNING,
            new State(true, true, true, false, true, true));
        show("idpSwitchWithoutTrust", Direction.IDP_SIGNING,
            new State(true, false, true, true, true, true));
        show("idpSwitched", Direction.IDP_SIGNING,
            new State(true, true, true, true, true, true));
        show("idpRetireTooSoon", Direction.IDP_SIGNING,
            new State(false, true, true, true, true, true));
        show("idpComplete", Direction.IDP_SIGNING,
            new State(false, true, true, true, false, true));

        show("spNoAdvertise", Direction.SP_SIGNING,
            new State(true, true, false, true, true, true));
        show("spIdpNotReady", Direction.SP_SIGNING,
            new State(true, false, true, true, true, true));
        show("spSwitched", Direction.SP_SIGNING,
            new State(true, true, true, true, false, true));

        show("decryptMissingOld", Direction.SP_ENCRYPTION,
            new State(false, true, true, true, true, true));
        show("decryptNewOK", Direction.SP_ENCRYPTION,
            new State(true, true, true, true, true, true));
        show("probesFail", Direction.SP_SIGNING,
            new State(true, true, true, true, false, false));
    }
}
~~~

**Chạy:**

~~~bash
javac SamlRolloverPlanner.java
java SamlRolloverPlanner
~~~

**Stdout mong đợi sau khi biên dịch thành công:**

~~~text
idpBaseline=IDP_OLD_ACCEPTED
idpPretrust=IDP_OLD_ACCEPTED
idpSwitchWithoutTrust=BLOCK_IDP_NEW_UNTRUSTED
idpSwitched=IDP_NEW_ACCEPTED_KEEP_OLD
idpRetireTooSoon=BLOCK_OLD_MESSAGE_IN_FLIGHT
idpComplete=IDP_NEW_ACCEPTED_CAN_RETIRE_OLD
spNoAdvertise=BLOCK_SP_NEW_UNADVERTISED
spIdpNotReady=BLOCK_SP_IDP_NOT_READY
spSwitched=SP_NEW_SIGNING_ACCEPTED
decryptMissingOld=BLOCK_INFLIGHT_OLD_DECRYPTION
decryptNewOK=SP_NEW_ENCRYPTION_ACTIVE
probesFail=HOLD_CANARY
~~~

**Giới hạn của demo:** `oldAvailable/newAvailable` nghĩa khác nhau theo Direction: tại IDP_SIGNING là SP verify certs; tại SP_SIGNING là IdP verify certs; tại SP_ENCRYPTION là SP private decrypt keys. `producerUsesNew` là signer IdP, signer SP hoặc encryption selector IdP. `newAdvertised` phải được xác nhận từ provider metadata/trust registry, `probesPass` phải đến từ IdP/SP sandbox tests thật. Demo không được dùng để kết luận login thực đã hoạt động chỉ vì in một dòng PASS.

## 14. Integration tests: chữ ký, issuer và encryption

Một suite thực cần có **IdP sandbox có private keys OLD/NEW riêng** và public certificates được SP trust. Mỗi negative case thay đúng một biến rồi **ký lại message bằng test signer hợp lệ** để kiểm riêng validator. Chỉ sửa XML sau khi ký sẽ khiến signature fail trước, không chứng minh `Audience`/`Recipient`/`InResponseTo` validation.

### 14.1. IdP signer tests

~~~text
IDP-OLD signs valid Response/Assertion  -> SP OLD+NEW trusts: ACCEPT
IDP-NEW signs valid Response/Assertion  -> SP OLD+NEW trusts: ACCEPT
UNKNOWN signs valid-looking Assertion   -> REJECT
IDP-NEW signs wrong Audience            -> REJECT
IDP-NEW signs wrong Destination         -> REJECT
IDP-NEW signs wrong Recipient           -> REJECT
IDP-NEW signs wrong InResponseTo        -> REJECT
IDP-NEW signs expired/replayed Response -> REJECT
~~~

**Không dùng `KeyInfo` self-trust.** Nếu IdP A/B có cùng subject, chỉ IdP signer của đúng registration/Issuer được phép verify.

### 14.2. SP signer tests

~~~text
SP-OLD signs AuthnRequest -> IdP trusts OLD: ACCEPT
SP-NEW signs AuthnRequest -> IdP trusts OLD+NEW: ACCEPT
SP-NEW signs AuthnRequest -> IdP trusts only OLD: REJECT
SP-NEW signs wrong Issuer -> IdP rejects
SP-NEW signs LogoutRequest -> IdP verifies
SP-NEW signs LogoutResponse -> IdP verifies
SP-UNKNOWN signer -> IdP rejects
~~~

### 14.3. Encryption tests

~~~text
IdP encrypts for ENC-OLD -> SP decrypt OLD+NEW: PASS
IdP encrypts for ENC-NEW -> SP decrypt OLD+NEW: PASS
IdP encrypts for ENC-NEW -> SP only OLD: FAIL
IdP encrypts for ENC-OLD -> SP only NEW: FAIL
IdP encrypts for unknown public key -> SP rejects
~~~

Sau decrypt phải chạy đầy đủ Assertion signature/Issuer/Audience/Recipient/time validation; giải mã được không đồng nghĩa authenticated.

## 15. Ma trận kiểm thử chấp nhận cuối cùng

| ID | Điều kiện | Expected |
| --- | --- | --- |
| I01 | IdP active OLD, SP verifier OLD | New SSO works |
| I02 | IdP active OLD, SP verifier OLD+NEW | SSO works |
| I03 | IdP active NEW, SP verifier OLD+NEW | SSO works |
| I04 | IdP active NEW, SP verifier only OLD | Reject, rollout gate fails |
| I05 | IdP still signs OLD, SP retires OLD early | Reject, not allowed |
| I06 | IdP-NEW signer in metadata but Spring not reloaded | Detect drift before activate |
| I07 | Multi-region IdP signs OLD/NEW simultaneously | SP trusts both, track per region |
| I08 | Unknown signer or wrong tenant | Reject |
| I09 | IdP-NEW signed wrong Audience | Reject |
| I10 | IdP-NEW signed wrong Recipient/Destination | Reject |
| I11 | IdP-NEW signed wrong InResponseTo | Reject |
| I12 | IdP-NEW signed expired Assertion | Reject |
| I13 | Replayed signed SAMLResponse | Reject |
| I14 | IdP-NEW signed LogoutRequest | SP verifies |
| I15 | IdP-NEW signed LogoutResponse | SP verifies |
| P01 | SP-OLD signs, IdP OLD trust | Pass |
| P02 | IdP trusts OLD+NEW, SP still signs OLD | Pass |
| P03 | SP switches NEW, IdP trusts OLD+NEW | Pass |
| P04 | SP switches NEW, IdP only trusts OLD | Fail, stop rollout |
| P05 | SP NEW cert not published to IdP | Block activation |
| P06 | SP private key doesn't match public cert | Fail, no unsigned fallback |
| P07 | SP-NEW with wrong Issuer/Destination | Reject |
| P08 | SP-NEW signs LogoutRequest/Response | IdP verifies each |
| P09 | One SP Pod still signs OLD in overlap | IdP accepts during window |
| P10 | IdP removes OLD before SP full switch | Detect stop/rollback |
| P11 | IdP single cert capability only | Coordinated cutover; no false zero downtime |
| E01 | IdP encrypts ENC-OLD; SP has OLD+NEW | Decrypt |
| E02 | IdP encrypts ENC-NEW; SP has OLD+NEW | Decrypt |
| E03 | IdP encrypts ENC-NEW; Pod B lacks NEW | Fail, rollout blocked |
| E04 | IdP encrypts ENC-OLD after SP removed OLD | Fail, retire too soon |
| E05 | Unknown public encryption key | Reject |
| E06 | Encrypted NameID/Attribute uses OLD | Dual decrypt during overlap |
| E07 | IdP chooses NEW immediately after metadata publish | SP NEW decrypt preinstalled on all nodes |
| E08 | Signing and encryption use same keypair | Test both directions independently |
| S01 | Existing user session during trust deploy | Continues per session-store policy |
| S02 | New login IDP-NEW after active switch | Authentication+authorization as expected |
| S03 | AuthnRequest before switch, Response after | Correlation and NEW signature pass |
| S04 | Pod A issues request, Pod B receives callback | Shared state or safe failure |
| S05 | SAML POST callback cookie SameSite | Real browser session works |
| S06 | SP entityID, IdP entityID, ACS unchanged | Metadata diff stable except approved certs |
| S07 | Metadata signature trust/validUntil fail | Reject invalid update |
| S08 | Cert rotation changes NameID/role mapping | QA fail, fix mapping |
| S09 | User authenticated but role denied | Correct 403, not crypto fault |
| S10 | Compromised OLD signing key | Remove trust per incident plan |
| S11 | SLO PartialLogout in rollout | Not report global success |
| S12 | TLS cert rotated concurrently | Test TLS separately |
| S13 | Direct backend forged Host/X-Forwarded | No attacker callback/trust |
| S14 | SP verification certs mixed across tenants | Reject cross-tenant message |
| S15 | Debug logs contain raw assertions/private keys | Security QA fail |

**Bằng chứng pass tối thiểu:** case ID, registrationId/issuer alias, sender key fingerprint alias, receiver effective trust aliases, node ID, signed message type, SAML protocol verdict, session result, user authorization verdict, redacted correlation ID, deployment version, expected/actual và reviewer. Không lưu raw SAML XML, NameID thật, private keys hoặc bearer cookies.

## 16. Những lỗi vận hành hay gặp

| Triệu chứng | Nguyên nhân khả dĩ | Điều tra |
| --- | --- | --- |
| 400/401 ngay sau IdP switch | SP verifier chưa trust IDP-NEW | Effective RPR/trust vs metadata URL |
| Chỉ một Pod thất bại | Static metadata/key secret chưa reload | Fingerprints/restarts per Pod |
| Metadata có NEW nhưng runtime vẫn OLD | Repository built at startup | Refresh/restart with approved metadata |
| SP NEW AuthnRequest bị IdP reject | IdP chưa trust SP-NEW | IdP effective trust/active signer |
| Login pass nhưng SLO fail | SLO signer/binding chưa test | Signed LogoutRequest/Response |
| EncryptedAssertion decrypt error | SP private ENC-NEW missing/mismatch | Mount/keypair/pod parity |
| Old encrypted Response fail sau switch | Removed ENC-OLD too early | Restore approved OLD decrypt if safe |
| Signing key cert expired | Renewal late/cert policy | Expiry alert/change window |
| SAML Audience changed unexpectedly | Entity ID drift in metadata | Compare SP/IdP registration |
| Recipient mismatch | ACS/public HTTPS/proxy drift | Fix canonical URL, not bypass |
| InResponseTo mismatch | Lost request state/SameSite/shared session | Browser and session repository |
| 403 after successful SAML auth | User role/tenant mismatch | Authorization mapping |
| Unexpected cert in metadata | Metadata provenance compromised or unapproved change | IAM verification/security incident |
| Old KeyDescriptor still present months later | Retirement unfinished | Audit trust remove with approval |
| IdP metadata signature cert rotated too | Separate metadata trust anchor switch | Do not trust XML unverified |
| SP signer key changed but no evidence | YAML/secret alias differs runtime | Actual signed AuthnRequest verification |
| Browser existing session works but new login fails | Existing sessions don't reverify Assertion | Test new SSO transactions |
| SAML signature algorithm mismatch | SP/IdP crypto policy drift | Algorithm capability tests |
| IdP one signing cert only | No dual trust feature | Coordinated change window |
| TLS cert swapped but SAML fails | TLS certificate ≠ SAML signer | Diagnose separate trust layers |
| Compromised OLD key in trust | Delayed incident response | Remove trust per security decision |

Không “chữa nhanh” bằng cách chấp nhận mọi signer, lấy cert từ untrusted `KeyInfo`, tắt Audience/Recipient/InResponseTo/replay/Signature validation, bỏ TLS hostname verification, hoặc cho phép `csrf.disable()` toàn app.

## 17. Rollback và emergency rotation

### 17.1. Rollback IdP signing

Có thể trở lại IDP-OLD chỉ khi:
- OLD key chưa compromise và còn cho phép dùng;
- IdP vẫn có private OLD signer, SP còn trust public OLD;
- Các nodes/regions được đồng bộ, SSO/SLO test pass;
- Rollback window và approvals vẫn hiệu lực.

Nếu SP đã retire OLD khỏi trust, rollback signer IdP về OLD **sẽ không hoạt động** trừ khi khôi phục verified trust trước. Nếu OLD bị lộ, không rollback dù gây outage: ưu tiên emergency recovery với key mới và reauthentication nếu cần.

### 17.2. Rollback SP signing

IdP phải còn trust SP-OLD. Rollback JAR hoặc đổi `sp-signing-active.key` sang OLD mà IdP đã gỡ OLD public cert có thể gây downtime. Rollback cần phối hợp **application version, IdP trust, secrets, metadata, TLS public URLs, session repository**, không chỉ deploy image cũ.

### 17.3. Rollback SP encryption

Khi IdP encrypts for ENC-NEW, một SP rollback image chỉ chứa ENC-OLD private key sẽ fail. Giữ both decrypt keys trong window nếu security policy cho phép; nếu phải chuyển IdP encrypt OLD, cần xét các SAMLResponses đã tạo bằng NEW đang in-flight. Không copy private key vào build artifact cho dễ rollback.

### 17.4. Compromise luôn là trường hợp đặc biệt

Nếu signer/decryption private key bị lộ, “giữ OLD để không gián đoạn login” có thể không an toàn. Security incident response quyết định remove trust nhanh, rotate credentials, audit suspicious Assertions/SLO events, revoke sessions và thông báo bên liên quan. Một certificate hết hạn nhưng chưa bị lộ là vấn đề khác; không đồng nhất expiration với compromise.

## 18. Runbook release theo người chịu trách nhiệm

**IAM/IdP team** chuẩn bị IDP-NEW, xác nhận active/secondary capability, metadata publication, trust signing policy, activation timestamp, rollback options.

**SP/app team** inventory registrations, current verifier/keys, deploy OLD+NEW trust/decryption, kiểm `RelyingPartyRegistration` effective, SSO/SLO validation, role mapping và user sessions.

**Platform team** quản lý secret mount, rolling reload/restart, cache TTL, shared session store, ingress HTTPS, node metrics, alarms và rollback route.

**Security team** xác minh algorithms, fingerprints, public certificate provenance, expiry, least-privilege secrets, key-compromise process và approve retirement.

### 18.1. Checkpoints

1. Có change record OLD/NEW fingerprints, owners, exact IdP/SP entityIDs.
2. Baseline signed SSO/SLO pass, trust keys documented, private keys stored safely.
3. IdP NEW public cert approved and published; SP OLD+NEW verification staged.
4. SP NEW signing public cert approved by IdP before SP active key changes.
5. SP ENC-NEW private decrypt key deployed to every SP Pod before IdP encryption switch.
6. Browser HTTPS/public ACS and SLO endpoints unchanged, no internal URL in metadata.
7. Metadata trust/refresh plan verified; all Pods have effective new keys.
8. Signed-by-OLD/NEW sandbox positive tests and unknown signer negative tests pass.
9. Canary run under representative traffic, no new SAML signature/decryption/correlation failures.
10. Active switch signed message evidence recorded, not just metadata status.
11. Old messages drained and rollback window closed; Security approves retirement.
12. Retired keys removed/revoked, metadata trust reduced, alerts enabled, logs sanitized.

### 18.2. Monitoring không lộ dữ liệu nhạy cảm

Ghi:
- environment, registrationId, IdP/SP alias, event type (SSO/LogoutRequest/LogoutResponse);
- SHA-256 public signer fingerprint **hoặc alias được phê duyệt**;
- signature verification outcome, decryption outcome, request ID fingerprint/correlation ID;
- wrong issuer/audience/recipient, replay/expiry category, HTTP status và node ID;
- transaction latency, key expiry/metadata refresh errors, user business authorization result.

Không ghi:
- private keys, `.p12`/`.key` files, raw `SAMLResponse`/`SAMLRequest`, XML plaintext assertions, NameID thật;
- `JSESSIONID`, browser cookies, `RelayState` raw nếu chứa state nhạy, CSRF tokens;
- full HAR, unredacted debug logs, credentials từ secret managers.

Test KeyInfo/signature bằng IdP sandbox/protocol validator; không cần thu raw browser Assertion trong hệ thống log production.

## 19. Bài tập và câu hỏi tự kiểm

**Bài A – ba chiều khóa.** Vẽ IdP→SP signatures, SP→IdP signatures, IdP encrypt→SP decrypt. Đánh dấu bên phải pretrust NEW trong mỗi trường hợp.

**Bài B – IdP signer switch quá sớm.** IdP đã ký NEW, SP Pod A/B trust OLD+NEW nhưng C chỉ OLD. Đưa ra quyết định gate, cách đo hiệu ứng theo Pod và kế hoạch sửa không dùng trust-all.

**Bài C – SP signer prepublish.** IdP chỉ biết SP-OLD; SP có NEW private signing key. Vì sao không thể switch ngay? Lập sequence publish/trust/activate/drain và test signed SLO.

**Bài D – encrypted response in flight.** IdP chuyển encrypt NEW lúc 10:00; browser còn một encrypted Assertion OLD lúc 09:59. SP nên giữ private key nào, và test nào chứng minh?

**Bài E – Java 17.** Chạy `SamlRolloverPlanner.java`, đối chiếu 12 dòng stdout. Thêm case NEW encryption public key advertised nhưng mọi SP nodes chưa có private key; giải thích blocker.

**Bài F – Spring YAML.** Đọc config `assertingparty.verification.credentials` OLD+NEW và `signing.credentials` active. Phân biệt verifier vs signer, giải thích vì sao list signing credentials không tự nói key nào active.

**Bài G – metadata refresh.** IdP metadata URL có NEW signer nhưng Spring `InMemoryRelyingPartyRegistrationRepository` chưa restart. Cách kiểm runtime trust và thực hiện rolling refresh an toàn là gì?

**Bài H – negative signer.** Test IdP-NEW signed wrong Audience. Phải ký lại fixture hay sửa XML sau signing? Tại sao?

**Bài I – multi-tenant.** IdP A và IdP B đều có user `alice`. Chứng minh cert NEW của A không thể verify assertion từ B bằng cách nào?

**Bài J – session continuity.** User đã login bằng OLD signer, SP phải restart Pod. Giải thích điều gì xảy ra với in-memory sessions vs shared sessions, InResponseTo và browser callback cookie.

**Bài K – SLO.** SP ký LogoutResponse NEW nhưng IdP chưa trust SP-NEW. SSO bình thường vì IdP không yêu cầu signed AuthnRequest. Test nào phát hiện bug?

**Bài L – compromised key.** OLD signer bị lộ trong overlap. Liệt kê hành động an toàn, tại sao “giữ OLD để login không lỗi” không còn hợp lệ?

**Bài M – cert fingerprints.** Dùng `openssl x509 -fingerprint -sha256 -dates` với public test certs; kiểm subject, NotAfter và signer alias, không xuất private key.

**Bài N – release gate.** Viết change report có old/new fingerprints, metadata TTL, effective trust per node, key activation time, browser E2E, SLO, encrypted Assertion, rollback và retirement approvals.

**Tiêu chí đạt:** Có thể thực hiện **IdP signing OLD→NEW với SP verification OLD+NEW được chuẩn bị trước**, **SP signing OLD→NEW với IdP verification ready**, **SP encryption OLD→NEW sau khi mọi SP decryptors có NEW và vẫn giữ OLD cho in-flight**; không làm sai entityID/ACS/SLO, không bypass signature/issuer/audience/correlation, có test và rollback rõ ràng.

## 20. Tài liệu tham khảo chính thức

- Spring Security 6.5 – SAML2 login overview, RelyingPartyRegistration and signing/decryption credentials: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security 6.5 – SAML2 Response authentication, signature and decryption: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html
- Spring Security 6.5 – SP metadata publication: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/metadata.html
- Spring Security 6.5 – SAML2 Single Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security 6.5 – RelyingPartyRegistration API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- Spring Boot 3.5 – Spring Security support: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS SAML2 Metadata – KeyDescriptor, SPSSODescriptor, IDPSSODescriptor: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML2 Core – signatures, Issuer/Audience, encrypted Assertions: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML2 Bindings – HTTP-POST/HTTP-Redirect: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- Microsoft Entra – Manage federation certificates and staged signing rollover: https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/tutorial-manage-certificates-for-federated-single-sign-on
- AWS IAM Identity Center – Rotate SAML certificates and provider limitations: https://docs.aws.amazon.com/singlesignon/latest/userguide/rotatesamlcert.html
- OWASP – Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
