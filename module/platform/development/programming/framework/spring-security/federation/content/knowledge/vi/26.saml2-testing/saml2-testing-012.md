# Kiểm thử làm mới metadata, luân chuyển khóa và nhiều đăng ký

> **Chủ đề:** Spring Security – federation. **Mạch kiến thức:** Kiểm thử SAML2. Bài Knowledge hướng dẫn kiểm thử toàn vòng đời cấu hình SAML 2.0 **Relying Party (RP/Service Provider – SP)** khi Identity Provider (IdP/Asserting Party – AP) **làm mới metadata**, **luân chuyển chứng thư/khóa**, và ứng dụng Spring Security vận hành **nhiều `RelyingPartyRegistration`**. Trọng tâm là bảo đảm **xác thực không gián đoạn trong kỳ luân chuyển hợp lệ** nhưng luôn **fail closed** với metadata giả, khóa không được tin, issuer/registration bị nhầm, assertion sai audience/recipient và thay đổi chưa được phê duyệt. Phạm vi chính: Java 17+, Spring Boot 3.x/Spring Security 6.4–6.5 và cách tiếp cận repository dựa trên OpenSAML 5 ở các phiên bản hỗ trợ; mọi ví dụ phiên bản khác được phân định rõ.

## 1. Mục tiêu học tập và kết quả cần kiểm chứng

Sau bài này, bạn có thể:

1. Giải thích các vai trò của `IdP metadata`, `SP metadata`, `RelyingPartyRegistration`, `registrationId`, `EntityID`, `ACS`, `SSO/SLO endpoint` và `KeyDescriptor`.
2. Phân biệt **đọc metadata một lần lúc khởi động**, **nạp lại khi cache hết hạn**, và **metadata resolver làm mới theo `cacheDuration`/`validUntil`**. Không mặc nhiên coi việc cấu hình một metadata URL là bật hot reload.
3. Thiết kế kiểm thử metadata signature/trust anchor, TLS/PKIX, tính hợp lệ thời gian, kích thước XML, redirects/SSRF, issuer/entityID, phiên bản cache và fallback khi mạng lỗi.
4. Phân biệt **IdP signing certificate** dùng SP kiểm chữ ký Response/Assertion, **SP signing certificate** dùng ký AuthnRequest/LogoutRequest, **SP decryption key** dùng giải mã Assertion, **metadata-signing certificate** để xác minh XML metadata, và **HTTPS certificate** để bảo vệ đường tải metadata.
5. Kiểm quy trình IdP rollover có **old + new verification keys đồng thời** trong giai đoạn overlap, rồi loại old key đúng thời điểm; kiểm cả thông tin mới được áp dụng thật trên các pods.
6. Kiểm luân chuyển **SP signing/decryption credentials** mà không tự suy rằng đổi IdP key là đổi SP key; xác nhận IdP đã nhận metadata SP mới trước khi chuyển khóa.
7. Cấu hình **hai hoặc nhiều RelyingPartyRegistration** và kiểm tách biệt `registrationId → IdP EntityID → SP EntityID → ACS → signing/decryption credentials → tenant authorization`.
8. Thiết kế **negative tests có ý nghĩa**: signed fixtures đúng khóa nhưng sai issuer/audience/recipient; metadata giả/expired; key mới chưa publish; rollback metadata; cross-tenant assertion; IdP-initiated SSO mơ hồ.
9. Dùng Spring Security SAML2 `SecurityFilterChain`, `saml2Metadata` và một repository nạp lại có kiểm soát. Biết giới hạn của `InMemoryRelyingPartyRegistrationRepository` và `CachingRelyingPartyRegistrationRepository`.
10. Viết/chạy một ví dụ **Java 17 độc lập** mô phỏng các policy gates của refresh, key overlap, version tăng và registration isolation, với stdout xác định. Ví dụ không thay thế XML Signature verification.
11. Lập runbook kiểm chứng trước/sau cutover, theo dõi cache TTL, chặn lỗi từng tenant và rollback có phê duyệt.
12. Định nghĩa các tiêu chí QA riêng cho **đúng metadata**, **đúng khóa**, **đúng registration**, **đúng SAML validation**, **đúng session/authorization**.

**Nguyên tắc xuyên suốt:** Metadata là một nguồn **cấu hình và trust policy**, không phải bằng chứng tự xác thực của user. Việc metadata mới được tải xuống **không có nghĩa nó đã được tin hoặc được kích hoạt**. Chỉ áp một snapshot sau khi xác minh nguồn, chính sách, thời hạn, tính nhất quán của EntityID/registration và phê duyệt thay đổi liên quan; tuyệt đối không tự học khóa ký SAML từ assertion chưa được xác minh.

## 2. Bối cảnh: một SP có hai IdP và hai tenant

Giả sử cổng `https://portal.example.org` có hai đối tác độc lập:

| Thành phần | Tenant North | Tenant South |
| --- | --- | --- |
| `registrationId` nội bộ | `north` | `south` |
| IdP EntityID (`Issuer` kỳ vọng) | `https://idp-north.example.net/saml` | `https://idp-south.example.net/saml` |
| IdP metadata URL | `https://idp-north.example.net/metadata` | `https://idp-south.example.net/metadata` |
| SSO endpoint | `https://idp-north.example.net/sso` | `https://idp-south.example.net/sso` |
| SP EntityID (`Audience` kỳ vọng) | `https://portal.example.org/saml/sp/north` | `https://portal.example.org/saml/sp/south` |
| ACS / Recipient | `https://portal.example.org/login/saml2/sso/north` | `https://portal.example.org/login/saml2/sso/south` |
| IdP trusted signing keys | `North-K1`, sau đó `North-K2` | `South-S1` |
| SP keys | `SP-North` (nếu cần ký/giải mã) | `SP-South` |
| Business tenant | `tenant-north` | `tenant-south` |

**Các chuỗi `North-K1` và `South-S1` chỉ là định danh minh họa**, không phải certificate hoặc key thực. Một thiết lập production cần các certificate đã được quản trị, quyền truy cập IdP staging, metadata hợp lệ, HTTPS, browser và Spring Boot project hoàn chỉnh.

Sơ đồ:

```text
                Browser and Spring Security RP
                            |
                  /saml2/authenticate/north
                  /saml2/authenticate/south
                            |
              +-------------+-------------+
              |                           |
          IdP North                   IdP South
     entityId=https://.../north     entityId=https://.../south
     signing key N1/N2               signing key S1
              |                           |
          SAMLResponse                SAMLResponse
              |                           |
              v                           v
     POST /login/saml2/sso/north   POST /login/saml2/sso/south
              |                           |
              +------------+--------------+
                           |
         Saml2WebSsoAuthenticationFilter
                           |
            RelyingPartyRegistration lookup
                           |
                  OpenSAML verification
                           |
              local account + tenant policy
```

Từ sơ đồ có ba sự khác biệt:

- `registrationId` là **khóa nội bộ** của Spring, có thể là `north` hoặc `south`; **không nhất thiết bằng** `Issuer`/EntityID của IdP.
- `SP EntityID` là audience của assertion và ID mà IdP dùng để định danh SP. Nó có thể là URI tùy ý đã đăng ký, **không mặc định là URL có thể truy cập được**.
- `ACS` là URL HTTP thực nhận `SAMLResponse`; nó phải phù hợp `Destination` và `SubjectConfirmationData.Recipient` theo profile/validator. Không biến `registrationId` trong URL thành bằng chứng user thuộc tenant đó khi chưa verify issuer, signature, audience và correlation.

## 3. Metadata SAML: cấu trúc và những gì phải kiểm

Metadata IdP là một XML document theo SAML 2.0 Metadata specification, ví dụ rút gọn:

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp-north.example.net/saml"
    validUntil="2030-01-10T00:00:00Z"
    cacheDuration="PT1H">

  <!-- Chữ ký METADATA có thể nằm tại đây khi được sử dụng.
       Không nhầm với signature của SAML Response. -->

  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_CERT_NORTH_K1</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_CERT_NORTH_K2</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp-north.example.net/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

**XML trên chỉ minh họa cấu trúc**, không phải metadata có thể dùng được: các certificate là ký hiệu, XML không được ký và IdP hostname không tồn tại trong lab tự động. Không đưa payload mẫu này vào production để bypass metadata signature policy.

### 3.1. Các trường phải được đọc đúng vai trò

| Thành phần metadata | Kiểm gì? | Rủi ro |
| --- | --- | --- |
| `EntityDescriptor@entityID` | Khớp IdP EntityID đã phê duyệt cho registration | Nhập metadata sai tenant/issuer |
| `EntitiesDescriptor` | Có thể gói nhiều entities, cần chọn entity duy nhất chính xác | Lấy nhầm IdP entity giữa nhiều partners |
| `IDPSSODescriptor` | Hỗ trợ protocol SAML2, bindings cần thiết | Không tương thích HTTP-POST/Redirect |
| `SingleSignOnService@Location` | HTTPS endpoint IdP allowlisted và đúng binding | SSRF/redirect tới host bất thường |
| `SingleLogoutService` | SLO endpoint và binding nếu dùng | Logout sai đối tác/DoS |
| `KeyDescriptor use="signing"` | Public key/certificate dùng verify SAML Response/Assertion | Tin nhầm key, fail hoặc impersonation |
| `KeyDescriptor use="encryption"` | Public cert IdP cho mục đích encryption nếu profile cần | Nhầm trust với response signing |
| Không có `use` trên `KeyDescriptor` | Theo metadata spec có thể dùng cho cả signing/encryption tùy policy | Import sai mục đích nếu code tự đọc |
| `validUntil` | Metadata instance còn hiệu lực đến thời gian nào | Chấp nhận metadata đã không hợp lệ |
| `cacheDuration` | Gợi ý thời gian cache trước khi cố làm mới | Lầm cache hết hạn = XML đã invalid |
| Chữ ký `ds:Signature` trên metadata | Xác minh bằng **metadata trust anchor** được thiết lập ngoài metadata | Metadata poisoning/key substitution |
| `<md:SPSSODescriptor>` của SP | EntityID, ACS và public signing/encryption cert SP | IdP dùng SP metadata cũ khiến luân chuyển SP key lỗi |

**Metadata signing key khác response signing key.** Một metadata document có thể được ký bởi authority/metadata aggregator thay vì IdP key hiện dùng ký assertion. Chỉ lấy một certificate xuất hiện bên trong metadata rồi dùng nó để chứng minh chính metadata đáng tin là **trust-on-first-use không có phê duyệt**, dẫn tới vòng lặp tin cậy.

### 3.2. Các ký hiệu “certificate” và “key” hay bị nhầm

| Tên thực thể | Ai giữ private key? | Ai cần public cert/trust? | Mục đích |
| --- | --- | --- | --- |
| **IdP Response/Assertion signing** | IdP | SP/RP | Verify XML Signature của SAMLResponse/Assertion |
| **IdP metadata signing** | IdP hoặc trusted metadata publisher | SP/RP có metadata verification trust anchor | Verify metadata XML |
| **IdP TLS HTTPS certificate** | HTTPS server/ingress IdP | JVM/HTTP client tải metadata | TLS server authentication/PKIX/hostname |
| **SP AuthnRequest signing** | SP/RP | IdP | Verify chữ ký AuthnRequest/LogoutRequest do SP gửi |
| **SP assertion decryption** | SP/RP | IdP cần SP public encryption cert | IdP mã hóa, SP giải mã EncryptedAssertion/EncryptedID |
| **SP TLS HTTPS certificate** | Ingress/backend của SP | Browser/IdP HTTP client tùy kết nối | HTTPS ACS/metadata endpoint |
| **Trusted CA/metadata publisher** | PKI/metadata authority | SP metadata trust store/verification credentials | Cấp trust anchors, không tự là SAML issuer |

Không nhập private key IdP vào SP. SP chỉ cần **public verification cert** để verify chữ ký IdP; SP signing/decryption private key phải được lưu ở KMS/keystore/secret mount do SP quản lý. Nếu một certificate được dùng cho nhiều mục đích, vẫn phải kiểm đúng purpose/policy, không suy các loại trust tương đương.

## 4. Ngữ nghĩa `validUntil` và `cacheDuration` theo OASIS

Đây là điểm dễ làm test sai nhất.

- `cacheDuration="PT1H"`: chỉ khoảng thời gian mà metadata consumer nên cache trước khi **thử refresh**. Nó không tự tuyên bố rằng metadata hết giá trị sau một giờ.
- `validUntil="2030-01-10T00:00:00Z"`: tại mốc đó, metadata instance **không còn được dùng**; metadata parent `EntitiesDescriptor` có hạn sớm hơn cũng ảnh hưởng hiệu lực.
- Metadata **quá cacheDuration nhưng vẫn trước validUntil** là *stale for refresh* nhưng có thể vẫn *valid for trust* theo chính sách. Tùy risk, consumer có thể tiếp tục dùng tạm bản hợp lệ cuối cùng khi fetch lỗi.
- Metadata **đã đến/vượt validUntil** phải bị xem **invalid**. Không cho cache TTL hay Redis entry giữ metadata vượt qua hard validity boundary.
- Nếu không có `validUntil`, không có nghĩa metadata tồn tại vĩnh viễn; cần **max age cứng của tổ chức**, signature trust, fetch policy và cảnh báo; tuy nhiên không tự gán một luật OASIS “mọi metadata không validUntil invalid” nếu hợp đồng không yêu cầu.
- `cacheDuration` trong `EntityDescriptor` có thể bị chính sách ở parent metadata ảnh hưởng. Không chỉ đọc thuộc tính đầu tiên qua regex rồi bỏ hierarchy.
- Cần đồng bộ clock UTC/NTP; `validUntil` là thời điểm tuyệt đối, không phải TTL tính từ lúc mỗi pod restart.
- Có thể có nhiều metadata entities, mỗi entity có validity/window khác; test **effective validity** cho đúng entity đã chọn.

### 4.1. Ví dụ timeline và quyết định

```text
Metadata North v1:
  retrievedAt = 09:00 UTC
  cacheDuration = PT1H
  validUntil = 13:00 UTC

09:30  -> cache age 30m; metadata vẫn valid.
10:01  -> đã vượt cacheDuration; cố làm mới.
10:02  -> fetch lỗi DNS; v1 vẫn còn trước validUntil.
          Có thể dùng LAST-KNOWN-GOOD theo policy đã phê duyệt.
12:59  -> nếu chưa refresh, vẫn trong hard validity window;
          phải báo alert và giới hạn stale fallback.
13:00  -> validUntil đạt: KHÔNG dùng v1 nữa.
13:01  -> fetch vẫn lỗi: chặn NEW SAML login / report incident,
          không bật tin khóa chưa được phê duyệt để cứu login.
```

Không hứa một resolver sẽ thực hiện chính xác mốc 10:01 dưới mọi framework hoặc scheduler; có thể có refresh jitter/backoff/async. Test **policy properties** và quan sát thực tế thời điểm refresh/activation thay vì chỉ giả định từ thuộc tính XML.

### 4.2. Khi IdP metadata endpoint không reachable

| Tình huống | Hành vi an toàn | Ghi chú |
| --- | --- | --- |
| Fetch timeout nhưng last-good metadata vẫn valid, trust đúng | Tiếp tục theo stale tolerance đã phê duyệt, alert | Không tự reload unsigned/new metadata |
| Last-good đã qua `validUntil` | **Không tin** snapshot quá hạn để verify login mới | Fail closed, cơ chế hỗ trợ user |
| Metadata thay đổi EntityID sang host lạ | Không kích hoạt tự động; review trust-boundary | Có thể bị tamper/misconfiguration |
| IdP gửi KeyDescriptor mới không theo lịch | Chặn hoặc quarantine theo policy, yêu cầu owner xác nhận | Metadata signed/trusted mới là điều kiện cần nhưng không đủ nếu quy trình yêu cầu approval |
| Metadata bị DNS redirect tới private IP/localhost | SSRF/network policy reject | Không follow redirect tự do |
| TLS certificate IdP hết hạn | Fetch không thành công theo PKIX | Không dùng `trustAll` |
| Signed metadata có signature invalid | Reject, giữ last-known-good nếu vẫn valid | Không dùng new cert bên trong metadata để verify cùng metadata đó |
| Cache eviction xảy ra đồng loạt trên các pods | Thundering herd/network storm | Jitter, single-flight, backoff và shared validated snapshot |
| IdP trả HTTP 200 nhưng XML không parse được | Reject candidate, không replace current state | HTTP 200 khác metadata trust pass |

## 5. Ba cơ chế nạp metadata cần phân biệt trong Spring Security

### 5.1. Cách A: đọc metadata khi tạo InMemory repository

Spring Security hỗ trợ:

```java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("https://idp-north.example.net/metadata")
        .registrationId("north")
        .build();

RelyingPartyRegistrationRepository repository =
    new InMemoryRelyingPartyRegistrationRepository(registration);
```

Một cách tương tự là dùng `spring.security.saml2.relyingparty.registration.<id>.assertingparty.metadata-uri` trong các phiên bản Boot hỗ trợ (xác minh property theo version).

**Nhưng:** `InMemoryRelyingPartyRegistrationRepository` lưu các registration objects đã được build; **không tự tải lại metadata định kỳ chỉ vì metadata ban đầu đến từ URL**. Nếu IdP publish N2 sau khi app start nhưng app chỉ giữ N1, response ký bằng N2 có thể bị từ chối cho tới khi repository được refresh/restart đúng cách.

### 5.2. Cách B: `CachingRelyingPartyRegistrationRepository`

Trong Spring Security từ 6.4, `CachingRelyingPartyRegistrationRepository` có thể nhận một **loader** tạo lại repository và quản lý cache bằng Spring Cache. Theo tài liệu Spring, cache không cấu hình expiry có thể giữ registrations vô hạn. **Cache TTL/eviction do bạn chọn** quyết định thời điểm loader được gọi lại.

Phân biệt:

```text
Startup -> loader fetches trusted IdP metadata -> Registration snapshot v1
  |
  +--> Cache hit: use v1
  |
  +--> Cache eviction / expiry:
          loader fetches metadata again
          -> validate candidate according to your trust policy
          -> create registrations v2
          -> cache v2
```

Nếu loader chỉ gọi `RelyingPartyRegistrations.fromMetadataLocation(url)`, nó **không tự tạo một chính sách metadata-signature verification độc lập**. Cần phân biệt “HTTPS URL đã được duyệt” với “XML metadata có chữ ký tin cậy”, và dùng pipeline ký/kiểm metadata thích hợp.

**Điểm QA:** gọi `cache.clear()` chỉ có thể buộc fetch lại; không chứng minh bản mới đáng tin, không xử lý `validUntil` tự động nếu cache provider không biết. Cần kiểm sau update: registration nào được trả về, fingerprint nào được dùng cho Response và tất cả pods đã hội tụ chưa.

### 5.3. Cách C: Asserting Party Metadata Repository/Resolver theo OpenSAML

Trong các phiên bản Spring Security hỗ trợ, `AssertingPartyMetadataRepository` cho phép tách metadata AP khỏi RP registration, và `OpenSaml5AssertingPartyMetadataRepository` dựa trên OpenSAML `MetadataResolver`, có khả năng làm mới theo expiry cùng xác minh metadata signature khi cấu hình verification credentials.

Đường ý tưởng:

```text
trusted metadata location or signed source
       |
       v
OpenSAML metadata resolver
       |
   parse / signature / validity / cache policy
       |
       v
AssertingPartyMetadataRepository
       |
       +--> AP metadata for North
       +--> AP metadata for South
       |
       v
RelyingPartyRegistrationRepository
       + fixed SP entityID, ACS, signing/decryption keys
       |
       v
SAML filter & provider
```

**Điểm quan trọng từ reference:** `OpenSaml5AssertingPartyMetadataRepository.withMetadataLocation(...).verificationCredentials(...)` có thể dùng để verify chữ ký XML metadata. **Nếu không cung cấp verification credentials, component không tự verify metadata signature.** `fromTrustedMetadataLocation(...)` dựa vào tính tin cậy của location theo giao thức/cấu hình, không được quảng cáo như “tự xác minh signature XML” mà không kiểm.

Cách C không làm mất nhu cầu: trust anchor bootstrap, SSRF protection, maximum response size, timeouts, `validUntil` policy, stable registrationId→entityID mapping, SP keys/ACS và bài test đa tenant. **Không trộn API của Spring Security 6.5, 7.1 và OpenSAML 4/5 mà không chọn đúng phiên bản.**

### 5.4. Bảng lựa chọn

| Thiết kế | Có refresh? | Ai quyết định trust/expiry? | Phù hợp |
| --- | --- | --- | --- |
| `InMemoryRelyingPartyRegistrationRepository` với metadata load lúc start | Không tự động | Config/release pipeline và logic nạp ban đầu | IdP ít thay đổi, restart theo runbook |
| `CachingRelyingPartyRegistrationRepository` + cache có TTL | Theo eviction/cache policy | Loader, signed metadata verifier, validation/approval service do bạn thiết kế | Một hoặc vài partners, có cache infrastructure và release policy |
| `OpenSaml5AssertingPartyMetadataRepository`/MetadataResolver | Theo resolver/expiry policy khi được cấu hình đúng | OpenSAML metadata trust/validity + RP mapping và external policy | Nhiều IdPs/metadata documents, cần lifecycle tốt hơn |
| Dynamic DB/service repository tự xây | Tùy implementation | App policy, DB consistency, signature verifier | Nhiều tenants, control plane riêng, yêu cầu atomic snapshot và audit |
| “GET XML mỗi request login rồi tin key trong XML” | Có nhưng nguy hiểm | Không có trust anchor/DoS limit nếu code sơ sài | **Không sử dụng** |

## 6. Các đường tin cậy khi cập nhật metadata

### 6.1. Không tự học khóa từ response SAML

Một tấn công kinh điển:

```text
Attacker creates unsigned/fake SAMLResponse
   |
   +-- embeds KeyInfo containing attacker certificate
   +-- uses Issuer="https://idp-north.example.net/saml"
   |
   v
Vulnerable SP extracts key from XML
   |
   v
Verifies signature against that same attacker key
   |
   v
Forged login accepted
```

Đúng phải là:

```text
Verified registrationId -> approved IdP entityID
     |
     v
Last-known-good trusted metadata / pinned certs
     |
     v
Trusted verification credentials for THAT IdP
     |
     v
Verify XML Signature over exact signed SAML nodes
     |
     v
Issuer + Audience + Destination + Recipient + Time
+ InResponseTo + request correlation + replay checks
     |
     v
Local account and tenant authorization
```

`KeyInfo` trong SAML XML là **đầu mối cho việc chọn key**, không phải nguồn tự cấp trust. Metadata mới phải được verify bằng **trust anchor đã cấu hình từ trước** hoặc kênh quản lý được phê duyệt; không lấy public key trong payload làm chứng cứ nó đáng tin.

### 6.2. Kiểm chữ ký metadata và TLS

- Tải metadata qua HTTPS với **hostname/SAN verification**, PKIX trust chain, thời hạn và phép kiểm phù hợp. Không tắt TLS verification vì một CA bị thiếu.
- Metadata có chữ ký XML thì SP xác minh signature với **metadata-signing verification credentials** đã thiết lập ngoài metadata. Metadata aggregator có thể dùng signing key khác IdP Response.
- Metadata có thể được quản lý bằng pinning/allowlist trusted location thay vì signed XML trong một số deployment, nhưng rủi ro trust khác; phải có trust contract và audit. **HTTPS từ hostname đúng không tự bằng metadata XML signature của publisher**.
- Pin expected `entityID`, SSO host/bindings và permitted signing algorithms; bất kỳ thay đổi bất thường nào phải được audit/approval theo risk.
- Nếu metadata chứa nhiều `EntityDescriptor`, phải chọn đúng entity theo ID được đăng ký, không lấy bản đầu tiên tùy ý.
- Chặn XML DTD/XXE, quá kích thước, deep nesting và signed XML wrapping bằng parser resolver đã được harden.
- Giới hạn redirect, kết nối ra ngoài, response size, DNS/IP (không tới loopback/link-local/metadata services), connect/read timeout và retry budgets.
- Không tải một URL metadata do browser truyền qua `?metadataUrl=...` hay HTTP Host.
- Không phân phối truststore/password/private key trong logs, metrics hay metadata HTTP response.
- Định nghĩa xử lý metadata hợp lệ nhưng có key chưa được phê duyệt: **quarantine** hoặc staged rollout theo security policy, không tự chuyển tất cả registrations.

### 6.3. Tại sao signature metadata không thay signature Response?

Một metadata document ký đúng chỉ nói **cấu hình IdP được authority đó xác nhận**, trong đó có public verification key(s). Từng `SAMLResponse` hoặc `Assertion` vẫn phải có XML Signature hợp lệ theo profile với **key được phép trong registration**, kèm issuer/audience/time/recipient. Không skip XML Signature chỉ vì metadata signed hoặc TLS protected.

Tương tự, SAMLResponse ký đúng bằng khóa North không chứng minh nó dành cho South; **registration isolation** vẫn phải kiểm trước khi tạo Authentication/tenant role.

## 7. IdP signing-key rollover: mô hình trước, trong và sau cutover

Giả sử North hiện ký Response bằng private key `N1`, và có kế hoạch chuyển sang `N2`. SP **chỉ giữ public certs** `N1-cert` và `N2-cert`.

### 7.1. Timeline chuẩn có giai đoạn overlap

```text
T0: IdP North signs SAMLResponse with N1.
    Metadata publishes only N1.
    SP trusts N1.              -> Login with N1 PASS.

T1: IdP publishes metadata containing BOTH N1 and N2
    while still signing with N1.
    SP fetches/trusts new metadata; verifies N1 and N2 are approved.
    SP trusts [N1,N2].         -> Login with N1 PASS; N2 ready.

T2: IdP switches to signing with N2.
    SP already trusts [N1,N2]. -> Login with N2 PASS.
    Some in-flight N1 responses may still arrive during overlap.

T3: After agreed grace period and in-flight lifetime,
    IdP removes N1 from metadata.
    SP refreshes and removes N1. -> N2 PASS; N1 FAIL.

T4: Audit and cleanup: N1 retired, caches/nodes verified,
    no stale trust of N1 remains.
```

Nếu khóa N1 **bị lộ**, không áp dụng grace period chỉ để tránh lỗi login. Cần response/metadata trust revoke theo incident, chặn N1 sớm nhất và điều phối IdP/SP emergency cutover.

### 7.2. Những kiểm thử không thể bỏ

| Trạng thái | Ký với N1 | Ký với N2 | Ký với key lạ NX |
| --- | --- | --- | --- |
| SP trusted set `{N1}` | PASS nếu toàn bộ SAML hợp lệ | **FAIL** | FAIL |
| SP trusted set `{N1,N2}` | PASS nếu còn hợp đồng | PASS | FAIL |
| SP trusted set `{N2}` | **FAIL** | PASS | FAIL |
| Metadata chứa `{N1,N2}` nhưng signature metadata invalid | Không được activate snapshot đó | Không được activate snapshot đó | FAIL |
| Metadata có `validUntil` quá hạn | Không được coi snapshot là trust source | Không được coi snapshot là trust source | FAIL |
| North response đưa vào South registration | **FAIL dù N1 hợp lệ ở North** | FAIL | FAIL |

Các chữ PASS trong bảng **giả định thêm** chữ ký được xác minh bằng XML Signature đúng node và mọi điều kiện SAML (issuer/audience/recipient/time/correlation) hợp lệ. Không test bằng cách sửa Base64 của một signed message sau khi ký rồi đổ lỗi “key mismatch”.

### 7.3. Vì sao “nạp thành công metadata” chưa đủ chứng minh rotation?

Các nguyên nhân phổ biến:

- Fetch lấy bản XML mới nhưng `InMemoryRelyingPartyRegistrationRepository` vẫn giữ registration cũ.
- Cache refresh một pod, các pod khác vẫn cache N1.
- Metadata mới đã có N2 nhưng custom code chỉ lấy **KeyDescriptor đầu tiên**.
- Parser bỏ `KeyDescriptor` vì use flags/trust policy không đúng.
- IdP đổi N2 trước khi cache TTL hết; SP chưa fetch.
- metadata signature verification fail, loader rollback về last-known-good N1; đây có thể là **hành vi an toàn nhưng không đạt availability**.
- Proxy/CDN cache metadata cũ dù source IdP đã đổi.
- `validUntil` của bản mới không được đánh giá hoặc timezone sai.
- Một app dùng certificate bundle tĩnh trong YAML override metadata keys động.
- IdP ký **Response** bằng N2 nhưng SP chỉ kiểm certificate N2 trên **Assertion** hoặc ngược lại theo provider; cần kiểm đúng signed-node policy.

**Định nghĩa PASS cho rotation:** Sau T2, signed Response hợp lệ bằng N2 được **đúng pod/registration** xác minh và tạo principal đúng tenant; sau T3, signed Response bằng N1 bị từ chối; key lạ luôn bị từ chối; không có unsigned fallback.

## 8. SP signing/decryption rotation: một trục độc lập

Khi SP thay khóa **AuthnRequest signing** hoặc **Assertion decryption**, thứ tự rollout thường ngược với IdP signing rotation.

### 8.1. SP ký AuthnRequest

- SP giữ private signing key, IdP giữ public verification certificate thông qua **SP metadata**/partner configuration.
- Trước khi SP chuyển sang ký bằng `SP-New`, **IdP phải tin public cert mới** và đã cập nhật đúng SP EntityID/registration policy.
- Giai đoạn overlap: IdP có thể chấp nhận SP-Old và SP-New theo chính sách; SP có thể chủ động chọn key ký mới.
- Test IdP thực sự verify signed AuthnRequest bằng key mới; không chỉ xem SP `/saml2/metadata/{registrationId}` có certificate mới.
- Sau cutover, IdP bỏ SP-Old theo lịch; khi bị lộ key cần xử lý incident.
- Với HTTP-Redirect binding, signature có thể nằm ở URL query với SigAlg/Signature theo binding, không chỉ XML embedded `ds:Signature`. Không dùng một XML verification tool tùy ý thay IDP binding verification.

### 8.2. SP giải mã EncryptedAssertion

- IdP dùng **SP public encryption certificate** để mã hóa assertion; SP giữ matching private decryption key.
- Trước khi IdP bắt đầu encrypt bằng SP-New, SP phải đã triển khai private decryption key mới trên **mọi pods**, trong khi có thể vẫn giữ key cũ để xử lý messages đang transit.
- Sau cutover, IdP encrypt bằng SP-New; SP test decrypt thành công. Khi hết vòng đời assertion cũ, loại SP-Old theo risk/policy.
- Test một encrypted fixture từ IdP thật; **Response signing verification thành công không đảm bảo decryption thành công**.
- `Saml2X509Credential.decryption(...)` khác `verification(...)`. Certificate công khai một mình **không** giải mã được.
- Với PKCS#11/HSM/KMS, kiểm key alias/key identifier và hỗ trợ algorithm; không coi thay file `.crt` tự thay private key.

### 8.3. Cùng certificate phục vụ nhiều mục đích?

Một số hệ thống tái dùng một keypair cho signing và decryption, nhưng không nên dựa vào đó mặc định. Khi tách khóa, rotation có thể diễn ra ở các ngày khác nhau. Bài test phải nêu rõ:

```text
IdP North signing response: N1 -> N2
SP North signing request:  SN1 -> SN2
SP North decrypting assertion: DN1 -> DN2
Metadata publisher signing: MN1 -> MN2
HTTPS server cert IdP:    TN1 -> TN2
```

**Năm luồng rotation khác nhau.** Một script “so SHA-256 fingerprint cũ và mới” là hữu ích nhưng **không** chứng minh trust/usage/tenant correctness. Metadata-signing key rollover có quy trình bootstrap riêng; không tự dùng new metadata signing cert xuất hiện trong chính metadata chưa được verify.

## 9. Nhiều registration: cần khóa ánh xạ cố định và cô lập tenant

`RelyingPartyRegistration` là một cấu hình **cặp SP ↔ IdP**, không chỉ một hostname. Trong Spring, `registrationId` là khóa để tìm đúng cặp. App có thể có:

```text
north:
  idpEntityId = https://idp-north.example.net/saml
  spEntityId  = https://portal.example.org/saml/sp/north
  acs         = https://portal.example.org/login/saml2/sso/north

south:
  idpEntityId = https://idp-south.example.net/saml
  spEntityId  = https://portal.example.org/saml/sp/south
  acs         = https://portal.example.org/login/saml2/sso/south
```

### 9.1. Những cặp phải kiểm đồng thời

1. `registrationId` khớp giá trị đã cấu hình, không lấy từ browser query để cấp tenant.
2. `Issuer` của SAML Response/Assertion khớp **expected IdP EntityID** theo registration.
3. XML Signature được verify bằng **trusted verification credentials của registration tương ứng**, không phải union keys của tất cả IdPs.
4. `AudienceRestriction` chứa **SP EntityID** tương ứng; một assertion North không có audience South chỉ vì gửi vào South ACS.
5. `Destination` của Response và `SubjectConfirmationData.Recipient` khớp **ACS public URL** được đăng ký; đúng scheme/host/path/binding.
6. `InResponseTo` tương quan đúng AuthnRequest thuộc phiên/registration đó (khi SP-initiated); không chấp nhận request ID của tenant khác.
7. `NotBefore`/`NotOnOrAfter`, conditions, replay/OneTimeUse, subject confirmation hợp lệ theo profile.
8. Decryption key nếu có thuộc SP registration tương ứng; không thử tất cả private keys từ mọi tenant rồi chấp nhận payload vào tenant bất kỳ.
9. Khi tạo principal, map `(issuer, stable NameID/subject) → internal account ID`; tenant quyền phải được kiểm từ source business đúng.
10. `registrationId` trên URL có thể được đoán hoặc sửa: **nó không vượt qua issuer/audience/recipient/signature checks**.
11. Khi một IdP có chung EntityID cho nhiều registrations, IdP-initiated SSO có thể mơ hồ. Dùng exact ACS/registration mapping đã thiết kế hoặc yêu cầu SP-initiated correlation; không tự chọn “first match”.
12. SLO metadata/LogoutRequest cũng phải match đúng registration và session, không chỉ chọn bằng issuer string.

### 9.2. Phân biệt `EntityID` và hostname

EntityID thường là một URI identifier, **không tự yêu cầu được HTTP GET**. Ví dụ cùng một SP public host có hai EntityIDs; điều đó hợp lệ nếu IdP registration đã cấu hình. ACS là URL HTTPS thực tế nhận POST. Việc ứng dụng có một hostname không có nghĩa nó chỉ có một registration.

Ngược lại, một IdP có thể phát metadata `EntitiesDescriptor` chứa nhiều `EntityDescriptor`. Đội tích hợp phải chọn đúng entityId đã phê duyệt, không lấy entity đầu tiên hoặc bản có certificate gần giống.

### 9.3. IdP-initiated SSO đặc biệt nhạy cảm

Trong unsolicited IdP-initiated response có thể **không có `InResponseTo`**. Nếu cùng một IdP EntityID phục vụ nhiều tenant/registrations và ACS route chung:

- Không có SP-initiated request state để xác định expected registration.
- Dò theo `Issuer` đơn lẻ có thể chỉ ra nhiều candidates.
- Dò từ `RelayState` do browser cung cấp cũng không đủ.
- Nên **không hỗ trợ trường hợp mơ hồ** hoặc dùng ACS/issuer-specific binding đã thiết kế và enforce signed audience/recipient.
- Không tự cấp quyền tenant dựa vào Domain suffix của NameID/email hoặc raw query `tenant=south`.
- Test login từ cả hai tenants cùng lúc và các response cross-post; kết quả phải không có tenant confusion.

## 10. Spring Boot 3.x: cấu hình tĩnh hai registrations có hai bộ key

**Phạm vi mẫu:** Spring Boot 3.5.x + Spring Security 6.5.x, Servlet, Java 17+; project cần IdP test, certificate files và credentials hợp lệ. Cấu hình ở mục này **tĩnh/được nạp khi application start**, không tự tuyên bố metadata URL refresh. Mục 12 mới mô tả repository refresh.

### 10.1. Dependency Maven

Trong POM có Spring Boot parent/BOM, Java 17:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
```

Đây là **fragment**, không phải một POM độc lập. Spring Security SAML2 phụ thuộc OpenSAML; tùy distribution/build repository, cần Shibboleth Releases qua artifact proxy đáng tin theo tài liệu Boot. Kiểm `./mvnw dependency:tree` để biết OpenSAML version thực tế và tránh vô tình trộn OpenSAML 4/5 hoặc Spring Security 6/7.

### 10.2. `application.yml` cho North/South

File `src/main/resources/application.yml`:

```yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

spring:
  security:
    saml2:
      relyingparty:
        registration:
          north:
            entity-id: "https://portal.example.org/saml/sp/north"
            acs:
              location: "https://portal.example.org/login/saml2/sso/north"
            assertingparty:
              entity-id: "https://idp-north.example.net/saml"
              sso-url: "https://idp-north.example.net/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/north-idp-N1.crt"
                  - certificate-location: "classpath:saml/north-idp-N2.crt"

          south:
            entity-id: "https://portal.example.org/saml/sp/south"
            acs:
              location: "https://portal.example.org/login/saml2/sso/south"
            assertingparty:
              entity-id: "https://idp-south.example.net/saml"
              sso-url: "https://idp-south.example.net/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/south-idp-S1.crt"
```

**Điểm QA:**

- `registration.north` và `registration.south` được Spring Boot bind thành hai RP configs.
- `entity-id` ở mức registration là **SP EntityID**; `assertingparty.entity-id` là **IdP EntityID**. Không đổi vị trí hai giá trị.
- `acs.location` phải đúng URL IdP phát Response tới; `Destination` và `Recipient` có thể kiểm với URL này.
- North có **hai public verification certificates** N1/N2 nhằm minh họa overlap. South chỉ có S1; **không thêm N1/N2 vào South** để xử lý sự cố North.
- Chứng thư `classpath:...crt` trong ví dụ là test fixtures. Production có thể tải từ secret/config store hoặc signed metadata; cần quản lý update và restart/refresh phù hợp. Đừng nhúng SP private signing/decryption key vào Git/JAR.
- Cấu hình trên **không yêu cầu ký AuthnRequest** hoặc decrypt Assertion. Nếu IdP yêu cầu chúng, thêm `signing.credentials`/`decryption.credentials` của SP với private key/cert đúng registration, rồi kiểm IdP metadata/behavior. Không tự bật insecure downgrade.
- `forward-headers-strategy` chỉ đáng tin khi reverse proxy xóa/viết lại `Forwarded`/`X-Forwarded-*`. Không tạo public ACS từ `Host` do browser tự gắn.
- Trong SAML Response, valid N1/N2 credential **chỉ là điều kiện kiểm chữ ký**, không tự chứng minh audience, recipient, issuer, session/correlation hoặc tenant.
- **Không** lấy ví dụ này làm cấu hình dynamic metadata; nó chỉ là snapshot giúp test rotation và tenant isolation với control plane triển khai theo release.

### 10.3. `SecurityFilterChain` và metadata SP

File `src/main/java/com/example/saml/TwoTenantSamlSecurity.java`:

```java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class TwoTenantSamlSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/tenant/north/**").authenticated()
                .requestMatchers("/tenant/south/**").authenticated()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
```

Đoạn trên khởi tạo SAML login và publish SP metadata, **chưa phải authorization tenant đầy đủ**: `authenticated()` chỉ đòi user đã login, không chứng minh user North được truy cập `/tenant/north/**`. Trong app thật phải nối application `AuthorizationManager`/`@PreAuthorize`/data permission checks với verified issuer+subject và local tenant memberships; request vào tenant sai phải 403/404 theo policy.

Các đường SAML thường gặp:

```text
/saml2/authenticate/north
/saml2/authenticate/south
/login/saml2/sso/north
/login/saml2/sso/south
/saml2/metadata
/saml2/metadata/north
/saml2/metadata/south
/saml2/service-provider-metadata/north
/saml2/service-provider-metadata/south
```

`/saml2/metadata` có thể publish metadata tổng hợp khi repository `Iterable`; per-registration endpoint phải trả đúng SP EntityID, ACS, credentials của đối tác. Khi metadata output dùng hostname sai sau reverse proxy, sửa canonical base URL/trusted forwarding, không tự sửa string trong XML đã ký.

### 10.4. Maven/run-time kiểm thử

```bash
./mvnw dependency:tree
./mvnw test
./mvnw spring-boot:run
```

Lệnh chỉ chạy thành công khi đã có Maven wrapper/project/IdP staging/test certificates thực và các placeholders được thay bằng cấu hình được quản trị; không có cách nào tạo signed SAML Response hợp lệ từ YAML này đơn độc.

## 11. Spring Security 6.4–6.5: nạp lại qua `CachingRelyingPartyRegistrationRepository`

Khi cần tự động fetch lại IdP metadata theo **cache expiry**, có thể xây một repository qua Spring Cache. Cần phân biệt **mô hình demo refresh** với **production metadata verification pipeline**.

### 11.1. Ý tưởng kiến trúc

```text
SecurityFilterChain
    |
    v
CachingRelyingPartyRegistrationRepository
    |
    +--> Spring Cache entry (lifetime configured)
    |
    +--> on miss:
            loader()
            -> fetch North metadata by approved URL
            -> fetch South metadata by approved URL
            -> parse and validate against trust policy
            -> construct immutable per-registration snapshots
            -> InMemoryRelyingPartyRegistrationRepository
    |
    v
findByRegistrationId("north" | "south")
```

**Điểm cảnh báo:** Nếu loader không kiểm metadata signature/validUntil/entityID/bindings và chưa có cơ chế last-known-good, một cache miss trong lúc IdP outage có thể gây lỗi login hoặc làm hệ thống đưa metadata không đáng tin vào cache. Không chạy code demo như hoàn chỉnh production security control.

### 11.2. Maven cho Caffeine Cache

Bên cạnh các dependencies ở mục 10, có thể thêm:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
<dependency>
  <groupId>com.github.ben-manes.caffeine</groupId>
  <artifactId>caffeine</artifactId>
</dependency>
```

Spring Boot BOM thường quản lý version cho Caffeine tương ứng; nếu project dùng BOM khác, cần thống nhất. Caffeine cache trong mẫu là **in-process**, mỗi pod có cache riêng và do đó **không** đồng bộ refresh lập tức với pod khác.

### 11.3. Java config: có TTL nhưng chưa tự verify metadata signature

File `src/main/java/com/example/saml/RefreshingSamlRegistrations.java`:

```java
package com.example.saml;

import java.time.Duration;
import java.util.concurrent.Callable;

import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.CachingRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.IterableRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

@Configuration
public class RefreshingSamlRegistrations {

    @Bean
    CacheManager samlCacheManager() {
        CaffeineCacheManager manager =
            new CaffeineCacheManager("trusted-saml-registrations");
        manager.setCaffeine(Caffeine.newBuilder()
            .expireAfterWrite(Duration.ofMinutes(15))
            .maximumSize(32));
        return manager;
    }

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations(
            CacheManager samlCacheManager) {

        Callable<IterableRelyingPartyRegistrationRepository> loader =
            () -> {
                // SOURCE LOCATIONS MUST BE FIXED AND PRE-APPROVED.
                // Production loader: verify metadata signature,
                // hard validUntil, expected entityIDs and endpoints,
                // trusted key changes and atomic publication.
                RelyingPartyRegistration north =
                    RelyingPartyRegistrations
                        .fromMetadataLocation(
                            "https://idp-north.example.net/metadata")
                        .registrationId("north")
                        .entityId(
                            "https://portal.example.org/saml/sp/north")
                        .assertionConsumerServiceLocation(
                            "https://portal.example.org/login/saml2/sso/north")
                        .build();

                RelyingPartyRegistration south =
                    RelyingPartyRegistrations
                        .fromMetadataLocation(
                            "https://idp-south.example.net/metadata")
                        .registrationId("south")
                        .entityId(
                            "https://portal.example.org/saml/sp/south")
                        .assertionConsumerServiceLocation(
                            "https://portal.example.org/login/saml2/sso/south")
                        .build();

                return new InMemoryRelyingPartyRegistrationRepository(
                    north, south);
            };

        CachingRelyingPartyRegistrationRepository registrations =
            new CachingRelyingPartyRegistrationRepository(loader);

        Cache cache = samlCacheManager.getCache(
            "trusted-saml-registrations");
        if (cache == null) {
            throw new IllegalStateException(
                "SAML metadata cache is not configured");
        }

        registrations.setCache(cache);
        return registrations;
    }
}
```

**Bắt buộc đọc các giới hạn của ví dụ:**

1. Class này là **mẫu kỹ thuật nạp lại**, cần dependencies, IdP metadata thực, trust store và hệ thống Spring Security; không chạy độc lập bằng `javac`.
2. `CachingRelyingPartyRegistrationRepository` dùng cache TTL 15 phút trong ví dụ. Đây **không phải mặc định của Spring Security** và cũng **không** bảo đảm đúng thời điểm `cacheDuration`/`validUntil` trong XML.
3. Dòng `fromMetadataLocation(...)` **không minh họa signed-metadata verification**. Với production có yêu cầu signed metadata, phải thay loader bằng pipeline đọc/trust metadata đã được xác minh hoặc dùng `OpenSaml5AssertingPartyMetadataRepository` với verification credentials ở version hỗ trợ.
4. Trên cache miss, code demo fetch **cả North và South**. Một IdP outage có thể ảnh hưởng cả hai registrations. Production có thể phân vùng refresh per registration để giảm blast radius, với atomic snapshot/version riêng.
5. Caffeine là per-JVM; nếu triển khai bốn pods, mỗi pod có thể refresh vào thời điểm khác nhau. Cần convergence test, jitter, alert, reconcile và health metrics.
6. Chưa xử lý stale last-known-good, failover snapshot, signature/EntityID review, audit hoặc hard `validUntil`. Vì thế **không được dùng nguyên mã mẫu làm bộ kiểm metadata đáng tin cậy**.
7. Khi cung cấp bean `RelyingPartyRegistrationRepository` như trên, nó sẽ **thay** repository Boot auto-configured từ `spring.security.saml2.relyingparty.registration.*`; không cấu hình đồng thời mà kỳ vọng hai nguồn được merge tự động.
8. Cache `maximumSize(32)` là ngân sách, không phải limit số IdP đăng ký. Nó là limit entries trong cache; hãy kiểm key semantics của Spring implementation.
9. Muốn giảm stale window, thiết kế monitor reload và thao tác invalidate có kiểm soát; không hạ TTL xuống vài ms để mọi request đăng nhập gọi IdP metadata URL.
10. Đừng dùng `@Scheduled` cập nhật từng field của mutable registration đang được authentication thread sử dụng; dựng object graph hợp lệ rồi **publish atomically**.

### 11.4. Test thời gian cache

Ví dụ cache TTL 15 phút:

```text
T0 = 10:00 app fetch North metadata v1 (N1)
T1 = 10:03 IdP publishes v2 (N1 + N2)
T2 = 10:05 login still uses cached v1 (N1 only)
T3 >= 10:15 cache may expire; loader can fetch v2 on use
T4 = after verified activation, login signed N2 may pass
```

**Test không dựa vào một Thread.sleep(15m) đơn lẻ.** Dùng fake clock/cache control, test eviction/refresh bằng metrics và signed SAML response thật. Sự kiện “cache entry expired” khác “trust list đã được cập nhật trên mọi nodes”.

## 12. OpenSAML metadata resolver và signed-metadata validation

Tài liệu Spring Security ở các phiên bản hỗ trợ `OpenSaml5AssertingPartyMetadataRepository` mô tả rõ metadata refresh nhờ `MetadataResolver` và option xác minh signature.

### 12.1. Fragment verify metadata signature

```java
// FRAGMENT dành cho Spring Security/OpenSAML version hỗ trợ.
// myMetadataVerificationCredential là public verification
// certificate được cấp qua trusted trust-bootstrap, KHÔNG lấy
// từ metadata vừa tải về.

OpenSaml5AssertingPartyMetadataRepository metadata =
    OpenSaml5AssertingPartyMetadataRepository
        .withMetadataLocation(
            "https://idp-north.example.net/metadata")
        .verificationCredentials(credentials ->
            credentials.add(myMetadataVerificationCredential))
        .build();
```

Phải bổ sung import/class/API theo đúng phiên bản thực. **Đây không phải một class Java độc lập**, và biến credential biểu diễn **chứng thư metadata-signing đã được xác minh ngoài luồng**. Nếu không cấu hình verification credentials, tài liệu Spring nêu rõ component **không thực hiện metadata signature verification**.

Một hướng khác là `fromTrustedMetadataLocation(...)`, trong đó trust dựa trên approved metadata location và kênh tải. Hãy đánh giá **đúng** bằng chứng trust (TLS/server identity/pinning/allowlist), không nhầm nó tự verify XML signature khi điều đó chưa được thiết lập.

### 12.2. Đừng tự ghép `entityId` và `registrationId`

Khi đọc metadata bằng `AssertingPartyMetadataRepository.findByEntityId(entityId)`, tham số là **IdP EntityID**, **không** mặc nhiên là Spring registrationId. Ví dụ:

```text
registrationId = north
expectedIdpEntityId = https://idp-north.example.net/saml

metadata.findByEntityId(
    "https://idp-north.example.net/saml")  -> candidate North
metadata.findByEntityId("north")           -> thường null
```

Nếu code tạo repository mới nhưng dùng `findByEntityId(registrationId)` như hai thứ luôn giống nhau, nó có thể chạy sai với tenant thật. Một dynamic repository cần bảng mapping cấu hình được phê duyệt:

```text
Map<String, TrustedIdpConfiguration>
  north -> (expected issuer/entityID, metadata location,
            SP entityID, ACS, SP credentials, trust anchors)
  south -> (...)
```

Nó lấy AP metadata theo expected EntityID, sau đó build RP registration với **registrationId cố định** và SP details cố định. Tính hợp lệ của metadata mới không được phép tùy ý đổi SP entityID, ACS hay tenant.

### 12.3. Bảo vệ phân phối bản metadata mới

Production cần:

- **Candidate:** tải XML có giới hạn byte/timeouts, parse secure, verify signature/TLS, check `validUntil`/allowed EntityID.
- **Validate:** kiểm KeyDescriptor usage/algorithms, SSO/SLO endpoints, collision/duplicate EntityIDs, registration mapping.
- **Stage:** tính danh sách key fingerprint thêm/bớt và policy diff; tùy risk đòi admin approval.
- **Activate:** tạo immutable metadata/registration snapshot, atomically publish per registration hoặc synchronized generation.
- **Observe:** log version, fingerprint hash/cert expiry, active registrations, refresh time, last-good age, failures — **không** log raw SAMLResponse/private keys.
- **Rollback:** chỉ về một snapshot **còn trusted và chưa expired**, theo version/approval. Không cho mạng lỗi khiến hệ quay về key đã thu hồi do compromise.
- **Reconcile:** kiểm mọi pods/regions đều đang dùng generation mong muốn trong SLA; nếu không, cô lập node lỗi và cảnh báo.

Một metadata resolver có thể cung cấp refresh/expiry logic, nhưng **quy trình approval/security policy không tự được framework thay cho tổ chức**. Thời gian refresh và nguồn tin cậy phải được kiểm bằng integration test cụ thể của phiên bản sử dụng.

## 13. Metadata của chính SP: phát hành và kiểm đúng từng registration

Spring Security `http.saml2Metadata(Customizer.withDefaults())` có thể publish SP metadata. Test:

1. `GET /saml2/metadata/north` có **SP EntityID North**, ACS North và public certs của SP North nếu đăng ký signing/decryption.
2. `GET /saml2/metadata/south` có SP EntityID South, ACS South và public certs SP South; không đưa public SP North key vào South trừ khi policy share key có phê duyệt.
3. `GET /saml2/metadata` có thể trả `<md:EntitiesDescriptor>` tổng hợp nếu repository `Iterable`. Không tự giả định một XML entity duy nhất khi có nhiều registrations.
4. Metadata phải trình bày public HTTPS URLs; nếu reverse proxy làm scheme thành HTTP, sửa trusted headers/static canonical URL.
5. Khi SP decryption cert đổi, metadata North xuất hiện public cert mới **trước** khi IdP bắt đầu encrypt bằng cert mới.
6. Khi SP signing cert đổi, IdP đã trust cert mới; signed AuthnRequest mới dùng đúng key.
7. `SingleLogoutService` nếu dùng phải match đúng route/registration, key và IdP policy.
8. Metadata endpoint không nên tiết lộ SP private key; `KeyDescriptor` chứa **public certificate** là hợp lệ theo spec.
9. Nếu dùng remote metadata cache ở IdP, test việc IdP đã refresh SP metadata — không chỉ tin `curl GET` SP metadata mới.
10. Khi registration bị xóa, endpoint riêng trả not-found và user không thể login với config cũ; local sessions/tokens đang tồn tại có lifecycle riêng theo policy.

Một RP có thể có nhiều IdPs chia sẻ SP EntityID/ACS trong một kiến trúc, nhưng dễ tạo ambiguity nếu custom lookup không đủ chặt. Tài liệu Spring hỗ trợ nhiều registrations; việc có chung ACS không tự làm đổi các điều kiện SAML Issuer/Audience/Response Destination và correlation.

## 14. Key overlap khác “trust tất cả certificate”

Về mặt cryptographic verification, SP có thể chấp nhận nhiều public IdP signing keys khi các keys đó thuộc **cùng trusted IdP/registration**. Điều này giúp overlap. Nhưng:

- Mỗi key phải được gắn với đúng IdP EntityID và certificate lifecycle.
- Không duyệt một root CA bất kỳ rồi chấp nhận mọi SAML signing certificate từ CA đó nếu policy đòi exact IdP signing credentials. X.509 chain trust của TLS và explicit SAML XML signing trust là các khái niệm khác.
- Không lấy mọi `KeyDescriptor` từ tất cả entities trong metadata aggregator để tạo một union global.
- Không nhầm `use="encryption"` với `use="signing"`.
- Không chấp nhận SHA-1/MD5 hoặc signatures yếu chỉ để làm N2 “tương thích”; signing algorithm policy phải rõ.
- Không bỏ `NotBefore/NotOnOrAfter`/`AudienceRestriction` để message ký bằng key mới qua.
- Không chấp nhận signed response từ issuer A rồi map vào tenant B chỉ vì certificate của A cũng nằm trong bộ trust chung.
- Không để old key N1 tồn tại vô thời hạn sau T3, kể cả bản metadata còn cache.
- Không làm “phương án khắc phục” bằng `acceptAnyIssuer`, `verifySignature(false)` hoặc skip conditions.

**Khóa cũ hợp lệ trong giai đoạn overlap** là một ngoại lệ có thời hạn và policy. Bản build/test cần chứng minh thời điểm/điều kiện N1 được gỡ, không chỉ trường hợp hai khóa đều được phép.

## 15. Java 17 độc lập: state machine mô phỏng refresh và multi-registration

Bài tập sau chạy được bằng **JDK 17**, không cần Spring, OpenSAML, XML hoặc IdP thật. Nó mô phỏng **policy gate sau khi một thành phần tin cậy đã xác minh metadata và SAML signature**. Nó **không** thực hiện XML Signature/metadata signature, HTTPS, replay/correlation hoặc SAML parsing; các biến boolean/fingerprint trong ví dụ chỉ là **fixture nội bộ**, tuyệt đối không lấy từ request browser.

### 15.1. File `SamlMetadataRolloverDemo.java`

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

public final class SamlMetadataRolloverDemo {

    enum Verdict {
        PASS_POLICY_ONLY,
        DENY_NO_REGISTRATION,
        DENY_METADATA_EXPIRED,
        DENY_REGISTRATION,
        DENY_ISSUER,
        DENY_KEY
    }

    record Snapshot(
        String registrationId,
        String idpEntityId,
        Set<String> allowedSigningKeys,
        long version,
        long validUntilEpochSecond,
        boolean metadataTrusted
    ) { }

    static final class Repository {
        private final AtomicReference<Map<String, Snapshot>> active =
            new AtomicReference<>(Map.of());

        boolean activate(Snapshot candidate, long now) {
            if (candidate == null
                    || !candidate.metadataTrusted()
                    || candidate.version() < 1
                    || candidate.validUntilEpochSecond() <= now
                    || candidate.allowedSigningKeys() == null
                    || candidate.allowedSigningKeys().isEmpty()) {
                return false;
            }

            while (true) {
                Map<String, Snapshot> before = active.get();
                Snapshot old = before.get(candidate.registrationId());

                if (old != null && candidate.version() <= old.version()) {
                    return false;
                }

                Map<String, Snapshot> next = new HashMap<>(before);
                next.put(candidate.registrationId(), candidate);

                if (active.compareAndSet(before, Map.copyOf(next))) {
                    return true;
                }
            }
        }

        Verdict decide(
                String routeRegistrationId,
                String resolvedRegistrationId,
                String responseIssuer,
                String presentedKeyId,
                long now) {

            Snapshot snapshot =
                active.get().get(resolvedRegistrationId);

            if (snapshot == null) {
                return Verdict.DENY_NO_REGISTRATION;
            }
            if (snapshot.validUntilEpochSecond() <= now) {
                return Verdict.DENY_METADATA_EXPIRED;
            }
            if (!snapshot.registrationId().equals(
                    routeRegistrationId)) {
                return Verdict.DENY_REGISTRATION;
            }
            if (!snapshot.idpEntityId().equals(responseIssuer)) {
                return Verdict.DENY_ISSUER;
            }
            if (!snapshot.allowedSigningKeys().contains(
                    presentedKeyId)) {
                return Verdict.DENY_KEY;
            }

            // Chỉ mô phỏng membership/key policy.
            // KHÔNG hề xác minh chữ ký XML thực!
            return Verdict.PASS_POLICY_ONLY;
        }
    }

    public static void main(String[] args) {
        long now = 1_900_000_000L;
        long future = now + 600;

        Snapshot northV1 = new Snapshot(
            "north", "https://idp-north.example.net/saml",
            Set.of("N1"), 1, future, true);

        Snapshot northV2 = new Snapshot(
            "north", "https://idp-north.example.net/saml",
            Set.of("N1", "N2"), 2, future, true);

        Snapshot northV3 = new Snapshot(
            "north", "https://idp-north.example.net/saml",
            Set.of("N2"), 3, future, true);

        Snapshot southV1 = new Snapshot(
            "south", "https://idp-south.example.net/saml",
            Set.of("S1"), 1, future, true);

        Repository repo = new Repository();

        System.out.println("installNorth=" +
            repo.activate(northV1, now));
        System.out.println("installSouth=" +
            repo.activate(southV1, now));

        System.out.println("northOldBefore=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N1", now));

        System.out.println("northNewBefore=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N2", now));

        System.out.println("refreshOverlap=" +
            repo.activate(northV2, now));

        System.out.println("northNewOverlap=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N2", now));

        System.out.println("northOldOverlap=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N1", now));

        System.out.println("wrongRegistration=" +
            repo.decide("south", "north",
                "https://idp-north.example.net/saml", "N2", now));

        System.out.println("wrongIssuer=" +
            repo.decide("north", "north",
                "https://idp-south.example.net/saml", "N2", now));

        System.out.println("northKeyOnSouth=" +
            repo.decide("south", "south",
                "https://idp-south.example.net/saml", "N2", now));

        System.out.println("rollbackOldVersion=" +
            repo.activate(northV1, now));

        Snapshot untrusted = new Snapshot(
            "north", "https://idp-north.example.net/saml",
            Set.of("ATTACKER"), 3, future, false);

        System.out.println("untrustedRefresh=" +
            repo.activate(untrusted, now));

        Snapshot expired = new Snapshot(
            "north", "https://idp-north.example.net/saml",
            Set.of("N2"), 3, now, true);

        System.out.println("expiredRefresh=" +
            repo.activate(expired, now));

        System.out.println("cutoverNewOnly=" +
            repo.activate(northV3, now));

        System.out.println("northOldAfterCutover=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N1", now));

        System.out.println("northNewAfterCutover=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N2", now));

        System.out.println("metadataExpiredAtBoundary=" +
            repo.decide("north", "north",
                "https://idp-north.example.net/saml", "N2", future));
    }
}
```

### 15.2. Lệnh biên dịch và stdout

```bash
javac --release 17 SamlMetadataRolloverDemo.java
java SamlMetadataRolloverDemo
```

Stdout xác định:

```text
installNorth=true
installSouth=true
northOldBefore=PASS_POLICY_ONLY
northNewBefore=DENY_KEY
refreshOverlap=true
northNewOverlap=PASS_POLICY_ONLY
northOldOverlap=PASS_POLICY_ONLY
wrongRegistration=DENY_REGISTRATION
wrongIssuer=DENY_ISSUER
northKeyOnSouth=DENY_KEY
rollbackOldVersion=false
untrustedRefresh=false
expiredRefresh=false
cutoverNewOnly=true
northOldAfterCutover=DENY_KEY
northNewAfterCutover=PASS_POLICY_ONLY
metadataExpiredAtBoundary=DENY_METADATA_EXPIRED
```

**Giải thích:**

- `installNorth/installSouth=true`: cài hai candidate snapshots *đã được giả định tin cậy*.
- `northOldBefore=PASS_POLICY_ONLY`: key ID N1 nằm trong North key set; **không phải kết quả verify XML Signature**.
- `northNewBefore=DENY_KEY`: N2 chưa được công bố/tin trong snapshot v1.
- `refreshOverlap=true`: kích hoạt North v2 có N1+N2.
- `northNewOverlap/northOldOverlap=PASS_POLICY_ONLY`: mô phỏng overlap.
- `wrongRegistration=DENY_REGISTRATION`: caller route South nhưng lookup North; không chấp nhận route/registration mismatch.
- `wrongIssuer=DENY_ISSUER`: response issuer không khớp IdP của North.
- `northKeyOnSouth=DENY_KEY`: North key không được dùng như South signing key.
- `rollbackOldVersion=false`: policy chặn snapshot version giảm hoặc bằng. Trong SAML metadata thực **không bắt buộc có version tăng**, nên cần control-plane generation/audit riêng nếu muốn bảo vệ rollback.
- `untrustedRefresh=false`: metadata giả không thể đưa key của attacker vào active set.
- `expiredRefresh=false`: candidate đã đến `validUntil` không được kích hoạt.
- `cutoverNewOnly=true`: kích hoạt bản N2-only.
- `northOldAfterCutover=DENY_KEY`: N1 bị gỡ sau cutover.
- `northNewAfterCutover=PASS_POLICY_ONLY`: N2 còn.
- `metadataExpiredAtBoundary=DENY_METADATA_EXPIRED`: khi `now == validUntil` phải fail closed.

**Giới hạn cực kỳ quan trọng:** Class chỉ so **string đại diện key IDs**, không đọc X.509/PKIX, không verify bất kỳ XML Signature nào, không parse SAML Assertion, không kiểm `AudienceRestriction`/`Destination`/`Recipient`/`InResponseTo`/time/replay. `metadataTrusted` là **giá trị mô phỏng**, không lấy từ HTTP header/query/browser. Production phải dùng OpenSAML/Spring Security và trusted metadata verification/authorization layer đúng phiên bản. `AtomicReference` minh họa atomic publication **trong một JVM**, không đảm bảo distributed consistency nhiều pods.

## 16. Kiểm thử refresh/rotation bằng signed fixtures thật

### 16.1. Nguyên tắc tạo fixtures

Muốn chứng minh **N2 accepted after refresh**, phải tạo một SAML Response **được ký thực sự bằng private key N2 trong IdP staging**, có đầy đủ:

- `Issuer=IdP North EntityID`;
- `AudienceRestriction` trỏ đúng SP North EntityID;
- `Destination`/`Recipient` đúng ACS North;
- `InResponseTo` phù hợp AuthnRequest North (nếu SP-initiated);
- `NotBefore/NotOnOrAfter` và bearer confirmation thời gian hợp lệ;
- XML Signature đúng node/phạm vi, thuật toán theo policy;
- `NameID`/attributes chỉ từ assertion đã verify;
- Optional `EncryptedAssertion` được SP North giải mã bằng key đúng.

Để test **wrong issuer với valid signature**, dùng một fixture được IdP test ký bằng key đã biết nhưng issuer/binding được tạo **trước khi ký** cho tình huống sai; không chỉ sửa chuỗi Issuer trong XML sau khi ký, vì khi đó signature cũng invalid, làm test không phân biệt được trust boundary.

Để test **metadata signature invalid**, có thể sửa metadata XML sau khi ký; ở đây mục tiêu là chứng minh metadata verifier reject. Nhưng để test `validUntil` hoặc policy rollback, hãy chuẩn bị metadata XML đã ký hợp lệ mang trường thời gian/version mong muốn (hoặc fake trusted metadata repository có clock control). Không vô tình biến toàn bộ negative tests thành “chữ ký sai”.

### 16.2. Hai tầng kiểm thử khác nhau

**Tầng A — metadata repository/control plane**

- Dùng metadata files/HTTPS stub, clock ảo và mock caches để kiểm fetch TTL/expiry/backoff/signature verification/candidate activation.
- Đầu ra là **trusted, mapped RP registrations**, không phải authenticated user.
- Không để external URL do browser điều khiển dùng trong test/prod fetch.
- Test multi-pod/cluster convergence và last-good fallback rõ mốc.

**Tầng B — SAML protocol/data plane**

- Dùng signed SAML Response fixtures và IdP staging/KDC? **Chỉ IdP SAML staging**; không trộn Kerberos.
- Test actual `Saml2WebSsoAuthenticationFilter` → `OpenSamlAuthenticationProvider` trên right registration.
- Đầu ra là `Saml2Authentication` đúng principal/roles/tenant hoặc authentication failure.
- Test message crypto, issuer/audience/recipient/correlation/time/replay khác với metadata fetch.
- Authenticated session trước rollout có thể vẫn sống dù metadata đã gỡ key cũ; key rotation chủ yếu ảnh hưởng **xác thực SAML mới**, còn session revocation là policy riêng.

### 16.3. Khi nào dùng MockMvc?

`MockMvc` thích hợp cho:

- Request path `/saml2/authenticate/{registrationId}`, ACS `/login/saml2/sso/{registrationId}`;
- Kiểm chooser page và metadata resolver route;
- Mock repository để chứng minh đúng registrationId được lookup;
- Test 400/401/redirect theo cấu hình failure handler;
- Test multi-registration domain/tenant authorization khi đã có authenticated principal.

Nhưng MockMvc **không** chứng minh remote HTTPS metadata fetch trust, TLS/PKIX, cache expiry của các pods, IdP signing key thật, hoặc message signing/metadata signature correctness nếu bạn chỉ mock provider. Cần end-to-end với IdP staging/valid test keys riêng.

## 17. Ma trận QA: metadata refresh, khóa và nhiều registrations

Mỗi ca ghi **registration, metadata generation/version, fingerprint signing key(s), IdP issuer, SP audience/ACS, signed test fixture ID và expected HTTP + authentication result**. Khi test key rollover, không log raw private keys, SAMLResponse hoặc bearer session cookies.

| Ca | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| **N1 normal** | North v1 metadata trust N1, SAML Response signed N1 | PASS sau toàn bộ SAML validation |
| **N2 before metadata** | North v1 chỉ trust N1, Response signed N2 | **FAIL** signature/key trust |
| **N1 after publish overlap** | North v2 verified metadata N1+N2 | PASS trong overlap theo policy |
| **N2 after publish overlap** | North v2 đã activated trên pod | PASS |
| **N1 after retirement** | North v3 chỉ N2, Response signed N1 | FAIL |
| **N2 after retirement** | North v3 chỉ N2 | PASS |
| **Unexpected N3** | Cert signer chưa trong trusted metadata | FAIL, không auto-learn |
| **Metadata URL 200 but XML invalid** | Candidate parse fail | Không replace valid current snapshot |
| **Metadata XML signature invalid** | Thay XML sau ký | Reject candidate |
| **Metadata unsigned when signed required** | Không có metadata ds:Signature | Reject candidate |
| **Metadata signing cert changed without bootstrap** | New metadata signed bằng untrusted cert | Reject; cần approved trust-anchor rollover |
| **Metadata validUntil future** | Signed metadata còn hiệu lực | Có thể activate nếu mọi checks khác pass |
| **Metadata validUntil exact now** | Current clock bằng expiration | Reject |
| **Metadata validUntil past** | Expired document | Reject, không fallback stale expired |
| **cacheDuration elapsed, still valid** | Fetch lỗi nhưng hard validity còn | Last-good behavior theo approved policy; alert |
| **cacheDuration elapsed, hard expired** | Fetch lỗi, past validUntil | Chặn login mới hoặc safe fallback theo chuẩn/trust policy, không dùng invalid metadata |
| **No validUntil** | Metadata valid under signature but no explicit expiry | Bounded max-age policy nếu tổ chức yêu cầu |
| **Parent EntitiesDescriptor earlier validity** | Child có validUntil muộn hơn parent | Áp effective earlier expiration |
| **Cache never expires** | Caching repository dùng default/no expiry | QA FAIL nếu requirement refresh; cấu hình TTL |
| **Cache expiry but new payload not applied** | Loader fetch xong nhưng repository stale | QA FAIL, debug cache/activation |
| **Cache refresh North fails** | North IdP metadata 5xx | South vẫn dùng được nếu kiến trúc cách ly |
| **Cache refresh all simultaneously** | 20 pods cùng fetch IdP | Rate/backoff/single-flight và availability theo SLA |
| **Cache race N1-v3 vs N1-v2** | Responses metadata tới lệch thứ tự | Không hồi sinh retired key; monotonic accepted generation |
| **One pod stale N1-only** | N2 cutover nhưng pod cũ | Detect drift, isolate/fail rollout; no silent bypass |
| **Metadata HTTPS certificate wrong SAN** | Fetch redirect/host mismatch | TLS verify fail, không trust-all |
| **Metadata SSRF to localhost** | URL bị thay bằng loopback/link-local | Egress allowlist reject |
| **Metadata oversized XML** | Metadata body vượt budget | Reject, không OOM |
| **Metadata XXE** | External entity/DTD | Reject/fail parse không network fetch |
| **Metadata duplicate entityID** | Hai entities same issuer trong aggregator | Reject/explicit disambiguation; no first-match |
| **Metadata switches issuer silently** | North URL trả South entityID | Quarantine/reject, không đổi tenant |
| **Metadata changes SSO endpoint host** | New host không trong approved endpoints | Alert/review; no automatic unsafe switch |
| **KeyDescriptor encryption-only** | New cert chỉ `use=encryption` | Không dùng verify assertion signature |
| **Two keys both verify North** | North N1+N2 | PASS nếu signature/issuer/audience hợp lệ |
| **North key sent to South** | South ACS, Response signed N1 | FAIL dù North có trust N1 |
| **South key signed with North issuer** | North ACS, signed S1 | FAIL |
| **North issuer in South registration** | South ACS + North Issuer | FAIL |
| **Valid North key wrong audience** | N2 signed, Audience=SP South | FAIL |
| **Valid North key wrong recipient** | N2 signed, Recipient=ACS South | FAIL |
| **Valid North key wrong destination** | N2 signed, Destination=ACS South | FAIL |
| **Replay North response** | Send same response again | Reject according to request correlation/replay policy |
| **InResponseTo from South used on North** | Matching key but wrong request state | FAIL |
| **IdP-initiated with ambiguous registration** | Shared EntityID and no state | Reject/explicit mapping, không chọn arbitrary |
| **IdP-initiated with unique mapping** | Policy cho phép, exact ACS/issuer/audience | PASS chỉ khi toàn bộ validation đạt |
| **SP signing rollover not published** | SP ký SN2 khi IdP chỉ tin SN1 | IdP reject AuthnRequest, staged rollout fail |
| **SP signing overlap** | IdP đã trust SN1/SN2, SP ký SN2 | PASS |
| **SP decryption key missing on one pod** | IdP encrypt DN2, pod thiếu key | Authentication/decryption fail; rollout gate catches |
| **SP decryption old ciphertext in flight** | Pod giữ DN1/DN2 theo policy | Decrypt đúng khi overlap |
| **SP metadata per registration** | GET /saml2/metadata/north | Đúng EntityID/ACS/public cert North |
| **SP metadata global** | GET /saml2/metadata | Iterable repository trả metadata cho đúng set registrations |
| **SP metadata wrong scheme** | Reverse proxy forwarded headers sai, ACS thành HTTP | QA FAIL, sửa trusted headers/canonical URLs |
| **SAML unsigned after refresh** | Metadata valid nhưng SAML Response unsigned | FAIL; no signature bypass |
| **Retired key still accepted** | T3 hoàn tất nhưng N1 vẫn pass trên pod | **Security QA FAIL**, cần invalidation/incident |
| **Unknown registrationId** | Browser POST /login/saml2/sso/unknown | Không đăng nhập; deny/failure path |
| **Same email different issuer** | North/South có same NameID/email | Không gộp local account/tenant trừ mapping approved |
| **Role from North used in South** | User North gửi North group claims tới tenant South | Local authorization deny |
| **Metadata download logs** | Debug fetch/rotation | Không log raw SAMLResponse/private keys; fingerprints/versions only |

**Điều kiện PASS tổng hợp:** Sau publish N2 + refresh, **đúng registration North** chấp nhận N2 trên mọi nodes; N1 chỉ được chấp nhận trong cửa sổ overlap, rồi **bị từ chối**; South vẫn tin **chỉ S1**; metadata không ký/sai/expired không bao giờ được activated; mọi Response vẫn phải pass XML Signature, issuer/audience/recipient/time/request correlation và tenant authorization.

## 18. Kịch bản end-to-end theo mốc thời gian

Đây là kế hoạch staging thực tế:

### Giai đoạn P0 — baseline

1. Chốt inventory IdP EntityIDs, metadata URLs, SP EntityIDs, ACS, SLO, registrations và certificates.
2. Ghi checksum/fingerprint SHA-256 certificate **public** và generation, không log private keys.
3. Xác minh clock đồng bộ, truststore TLS metadata fetch và metadata signature trust policy.
4. Khởi tạo North v1 trust N1, South v1 trust S1.
5. Login SP-initiated từ North/South mỗi nơi một user test; kiểm issuer, audience, recipient, tenant.
6. Thu thập login success/failure by registration, pod, key fingerprint label.
7. Test negative unknown registration, wrong tenant, wrong key và expired assertion.

### Giai đoạn P1 — prepublish N2

1. IdP North phát certificate N2 vào signed/trusted metadata trong khi vẫn ký SAMLResponse bằng N1.
2. SP fetch candidate, kiểm XML signature/EntityID/validity/endpoint diff.
3. Security owner xác nhận N2 theo change record hoặc policy đã phê duyệt.
4. Apply immutable snapshot North N1+N2; South không đổi.
5. Kiểm tất cả pods báo generation v2/expected fingerprints.
6. Login N1 từ IdP vẫn pass; tạo signed fixture N2 từ IdP staging để chứng minh N2 đã được tin.
7. Thử key NX chưa đăng ký bị reject.

### Giai đoạn P2 — actual cutover

1. IdP North chuyển signing key active sang N2.
2. Test browser SP-initiated SSO North, signed response N2 đúng issuer/audience/recipient.
3. Test SAML responses in-flight bằng N1 còn pass nếu overlap policy cho phép.
4. Test South không gián đoạn; North N2 không được coi là South S1.
5. Kiểm metadata refresh/keys đã áp ở mọi pods; không chỉ trên node kiểm thử.
6. Có canary và route rollback trong phạm vi security, không tắt signature verification để cứu login.

### Giai đoạn P3 — retire N1

1. Chờ hết in-flight Response/AuthnRequest theo policy và xác nhận không còn đối tác dùng N1.
2. IdP publish metadata chỉ N2, SP fetch và activate generation v3.
3. Test North response signed N1 **bị reject** trên mọi pods, N2 vẫn pass.
4. Remove N1 khỏi pinned/static cert files, caches, deployment manifests nếu không cần.
5. Kiểm South S1 vẫn pass, đặc biệt nếu shared infrastructure/caches.
6. Kết thúc change record với audit bằng chứng.
7. Nếu N1 bị lộ, bỏ qua overlap grace theo incident commander; chặn mọi N1 ngay sau trusted emergency revoke.

## 19. Negative tests về nguồn metadata và vận hành

### 19.1. HTTP metadata endpoint trả redirect

Một metadata URL có thể trả 301/302 đến hostname khác. Không tự follow vô hạn. Cần:

- Allowlist exact hostnames/IP networks và permitted redirect targets.
- Phân biệt proxy/CDN rewrite hợp lệ với DNS rebinding/SSRF.
- Giữ HTTPS, TLS SAN/hostname verification và timeouts.
- Reject HTTP downgrade, loopback, link-local và cloud instance metadata endpoints.
- Validate metadata signing trust sau khi tải, không coi redirect URL là IdP EntityID.
- Test không cho browser `?url=...` thay metadata location server-side.

### 19.2. Cache/outage và khả năng khôi phục

Khi outage:

- Cache TTL expires trước hard validUntil: có thể dùng last-known-good **đã trusted và chưa hết hiệu lực** theo stale fallback policy, đồng thời alert.
- Hard validUntil đã qua: không dùng bản invalid; new login cần fail closed với error page sanitized và service support.
- Metadata candidate mới sai signature/issuer: giữ last-good nếu vẫn valid, quarantine candidate.
- Cache corruption/Redis outage: không tái tạo trust config từ user input hoặc lấy key trong SAMLResponse.
- Metadata signing key rollover: cần trust-anchor migration approved. Không tự đặt “allow any certificate” hoặc tắt metadata signature check.

### 19.3. Chẩn đoán lỗi từ đúng tầng

| Lỗi | Tầng | Dấu hiệu | Cách xử lý |
| --- | --- | --- | --- |
| `PKIX path building failed` khi tải metadata | HTTPS fetch | JVM không tin metadata server TLS cert | Sửa đúng CA/chain/truststore fetch |
| `metadata signature invalid` | XML metadata trust | Candidate không được activate | Kiểm metadata publisher signing cert/trust |
| `metadata past validUntil` | Metadata validity | Candidate/current snapshot expired | Fetch bản hợp lệ hoặc fail closed |
| `unknown entityID` | Mapping | Candidate issuer không khớp approved IdP | Kiểm registration mapping, không auto reassign |
| `Unknown registrationId` | RP repository | Route/selector không tồn tại | Kiểm URL/config, không fallback tenant khác |
| `SAML response signature invalid` | OpenSAML | N2 key chưa được trusted/fixture invalid | Kiểm IdP active signer, SP accepted key fingerprints |
| `InvalidDestination`/Recipient mismatch | Browser ACS/proxy | Public URL/config lệch | Sửa canonical ACS/trusted Forwarded headers |
| `InvalidAudience` | Assertion Conditions | SP EntityID khác đăng ký | So RP EntityID và IdP audience |
| `InResponseTo mismatch` | Request correlation | Wrong/old saved request state | Kiểm session, registration and AuthnRequest ID |
| Decrypt error | SP private decryption key | DN2 chưa deploy all nodes | Đồng bộ secret aliases/private keys |
| Login fail chỉ một pod | Cache drift | Different key/metadata generation | Measure per-pod versions, gate rollout |
| Login fail chỉ North | Partner-specific metadata/cache | North IdP outage hoặc key mismatch | Không thay South trust keys |
| IdP rejects AuthnRequest | SP signing key | IdP chưa biết SN2 | Publish SP metadata, IdP confirm |
| Metadata endpoint SP sai ACS | Outbound metadata | Proxy Host/Proto yanlış | Fix trusted headers/static URL, retest |
| Signer N1 vẫn pass sau retirement | Cached trust stale | Old key still trusted on a pod | Invalidate safely, quarantine pod, investigate |
| Same IdP issuer in two regs | Lookup ambiguity | IdP-initiated response chọn sai | Require exact routing/request state, avoid arbitrary lookup |
| Metadata refresh storm | Cache TTL synchronized | IdP overload; pods fetch concurrently | Add jitter/backoff/shared validated snapshot |
| User North gets tenant South data | Business authorization | Map claims across tenants improperly | Fix local issuer+subject mapping/tenant auth |

**Không chữa lỗi bằng cách mở rộng validation globally.** Một Response đúng N2 nhưng sai audience không được chấp nhận do “đang rotation”. Metadata mới từ North không thể tự đổi `registrationId` sang South. Một certificate không đáng tin không được import vào mọi registrations để giảm hỗ trợ người dùng.

## 20. Quan sát và báo cáo QA không làm rò bí mật

Các trường telemetry hữu ích:

```text
utcTimestamp
registrationId (bounded allowlist)
approvedIdpEntityId (normalized)
metadataSourceId
metadataGeneration
metadataETag (only if trusted)
metadataFetchedAt
metadataCacheAgeSeconds
metadataValidUntil
metadataSignatureVerified
metadataTrustAnchorFingerprintSha256
keySetFingerprintSha256 (public certificates only)
keyCountAndUsage
activationDecision
refreshFailureReason
activePodOrRegion
samlResponseVerificationDecision
assertionIssuerMatch
audienceAndRecipientMatch
inResponseToCorrelation
localTenantAuthorizationDecision
changeTicketId
traceId
```

Không log:

```text
Raw SAMLResponse / Base64 XML
Full Assertion and NameID/attributes with personal data
Private key PEM, PKCS#8, keystore password
SAML Response SignatureValue or replayable artifacts
Session cookie / JSESSIONID
AuthnRequest raw query/signature if audit leaks user/session context
Full signed metadata XML dump in ordinary request logs
```

Public key fingerprint SHA-256 có thể dùng để so bản cũ/mới nhưng không nên biến issuer/NameID tùy ý thành Prometheus labels có cardinality vô hạn. Khi báo “refresh successful”, phải chỉ rõ **fetched, verified, activated, observed on pods** là các sự kiện khác nhau.

### 20.1. Chỉ số vận hành

- `saml_metadata_fetch_total{registration,outcome}`
- `saml_metadata_signature_failures_total{registration}`
- `saml_metadata_validity_seconds{registration}`
- `saml_metadata_age_seconds{registration,pod}`
- `saml_registration_generation{registration,pod}`
- `saml_signer_verification_failures_total{registration,keyCategory}`
- `saml_rollover_old_key_accept_total{registration}` (cần về 0 sau T3)
- `saml_login_failure_total{registration,reason}`
- `saml_audience_recipient_mismatch_total{registration}`
- `saml_metadata_refresh_lag_seconds{registration}`
- `saml_metadata_rollback_rejected_total{registration}`
- `saml_partner_key_change_alert_total{registration}`

**Đây là đề xuất metrics**, không phải tên Micrometer/Spring built-in có sẵn. Muốn có các metrics này phải instrument đúng lớp với PII filtering, cardinality bounds và retention.

## 21. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Spring dùng `RelyingPartyRegistrations.fromMetadataLocation(url)` rồi lưu vào `InMemoryRelyingPartyRegistrationRepository`. IdP publish khóa N2 sau startup. Ứng dụng tự biết N2 ngay không?

**Đáp án:** Không. Repository giữ snapshot đã build; cần restart/rebuild/refresh qua cache/resolver được thiết kế. Test phải kiểm trusted keys thực sự thay đổi, không chỉ URL fetch 200.

**Câu 2.** `cacheDuration` đã hết, nhưng `validUntil` còn tương lai và metadata endpoint bị lỗi. Có bắt buộc phải coi metadata không hợp lệ ngay không?

**Đáp án:** Không. `cacheDuration` là thời điểm nên thử refresh, khác với hard validity. Last-known-good vẫn có thể được dùng theo stale policy khi còn valid; nếu đã tới `validUntil`, không dùng nữa.

**Câu 3.** IdP North chuyển N2 nhưng metadata của SP South vô tình cũng chứa certificate N2. Có thể cho North Response đăng nhập South không?

**Đáp án:** Không. Đây là trust-config leak. Keys phải gắn với đúng IdP/registration; South Response phải pass issuer, signature, audience, recipient, correlation và tenant policy của South.

**Câu 4.** XML metadata có certificate N2 trong `KeyDescriptor`. Có đủ để tự động tin N2 không?

**Đáp án:** Chưa. Metadata document/source phải được xác minh theo trust contract (signed metadata/trusted location), validUntil/issuer/EntityID/endpoint/key usage và approval. Không dùng certificate trong chính metadata để tự chứng minh metadata hợp lệ.

**Câu 5.** HTTPS certificate IdP đổi thành TN2 và browser TLS vẫn xanh. Liệu Response signing certificate N1 cũng tự đổi không?

**Đáp án:** Không. HTTPS TLS cert và SAML signing cert là hai trục khác; cần kiểm đúng KeyDescriptor/Response Signature.

**Câu 6.** IdP ký SAMLResponse bằng N2 nhưng SP vẫn chưa activate metadata N1+N2. Hành vi đúng?

**Đáp án:** Reject Response ký N2 theo trust list hiện hành. Khắc phục bằng kế hoạch prepublish/verified refresh trước khi switch, không disable signature verification.

**Câu 7.** Khi SP xoay decryption key DN1→DN2, IdP chưa biết public DN2 nhưng SP đã xóa DN1. Có thể lỗi gì?

**Đáp án:** IdP vẫn encrypt bằng DN1 public certificate, SP không có DN1 private key để decrypt; login fail. Thứ tự đúng là SP deploy DN2 private key song song DN1, IdP refresh SP metadata rồi chuyển encryption, sau đó mới retire DN1.

**Câu 8.** `registrationId=north` có bằng `Issuer=https://idp-north.example.net/saml` không?

**Đáp án:** Không. Một là Spring internal key, một là IdP SAML EntityID. Dynamic repository dùng `findByEntityId` phải truyền EntityID thật, không truyền registrationId trừ trường hợp ngẫu nhiên bằng nhau.

**Câu 9.** Một signed Response N2 hợp lệ về signature nhưng `AudienceRestriction` trỏ SP South, POST vào ACS North. Có chấp nhận không?

**Đáp án:** Không. XML Signature không thay kiểm audience/recipient/destination và request correlation.

**Câu 10.** Spring Security công bố `/saml2/metadata/north` mới, có thể kết luận IdP đã dùng khóa SP signing mới chưa?

**Đáp án:** Không. IdP phải nhận/refresh SP metadata và xác minh AuthnRequest thực tế. Test end-to-end sau switch là bắt buộc.

**Câu 11.** Cache ở pod A đã refresh North N2 nhưng pod B vẫn chỉ N1; 50% logins lỗi. Có thể báo rollover hoàn tất không?

**Đáp án:** Không. Phải kiểm convergence theo pod, isolate node stale, cân chỉnh cache/rollout. Đồng thời không mở trust quá rộng.

**Câu 12.** Metadata XML signer bị thay đổi nhưng message SAML signer không thay. Cần cập nhật trust gì?

**Đáp án:** Cần quy trình luân chuyển **metadata-signing trust anchor** riêng cho metadata resolver, không tự thay IdP response verification key hoặc TLS truststore theo suy đoán.

**Câu 13.** IdP-initiated response có `Issuer` giống nhau cho hai registrations nhưng không có `InResponseTo`. Nên chọn registration đầu tiên?

**Đáp án:** Không. Phải có routing/ACS/audience policy không mơ hồ hoặc từ chối unsupported unsolicited flow; không chọn tùy ý theo thứ tự list.

**Câu 14.** Muốn unit-test luân chuyển metadata nên sửa signed XML sau khi ký rồi xem Spring reject; có chứng minh khóa mới hoạt động không?

**Đáp án:** Không. Đó chỉ test signature invalid. Phải phát/nhận signed fixture đúng N2 từ IdP test, verify full SAML policy sau refresh.

## 22. Checklist production cho bài kiểm thử này

- [ ] Inventory mọi `RelyingPartyRegistration`: registrationId, expected IdP EntityID, SP EntityID, ACS, SLO, signing/decryption credentials và tenant mapping.
- [ ] Source metadata locations cố định/allowlisted; không lấy URL từ browser/Host/RelayState.
- [ ] HTTPS metadata fetch có PKIX/SAN/hostname verification, timeouts, limits, redirect/SSRF controls; không `trustAll`.
- [ ] XML metadata parser cấm XXE/DTD nguy hiểm, có size/depth/complexity limits.
- [ ] Signed metadata verification hoặc approved trusted-location policy được xác định; không lấy trust key từ metadata chưa verify.
- [ ] Metadata signature verification credentials khác SAML Response verification credentials khi policy phân tách.
- [ ] Metadata `entityID` được pin theo registration; `EntitiesDescriptor` nhiều entities không bị chọn first-match.
- [ ] `validUntil` có hard expiry; `cacheDuration` dùng lịch thử refresh, không nhầm cache staleness với validity.
- [ ] Last-known-good chỉ được dùng trong hard validity window và theo risk policy, có alert.
- [ ] `InMemoryRelyingPartyRegistrationRepository` không bị hiểu sai là hot reload metadata.
- [ ] `CachingRelyingPartyRegistrationRepository` có TTL/expiry thực; default cache vô hạn không đáp ứng requirement refresh.
- [ ] OpenSAML metadata resolver/signature verification được cấu hình đúng version, kiểm từ docs/test, không mix 6.x/7.x APIs.
- [ ] Repository/metadata snapshot được publish atomically sau verify/approval; không chỉnh object đang dùng giữa authentication threads.
- [ ] Các pods/regions có metrics version/fingerprint và convergence SLA, không có cache drift trước IdP cutover.
- [ ] IdP signing rollover có kế hoạch N1→N1+N2→N2; prepublish key trước switch, kiểm N1 bị reject sau retirement.
- [ ] Unknown/unapproved SAML signing certificate không được tự trust nhờ KeyInfo hoặc regex XML.
- [ ] Metadata signing certificate rollover có trust-anchor bootstrap độc lập; HTTPS/TLS cert rotation không đồng nghĩa ký SAML.
- [ ] SP signing key rollover được IdP công nhận trước switch; AuthnRequest signed test bằng key mới.
- [ ] SP decryption key rollover giữ private old/new trong window hợp lệ, test EncryptedAssertion và mọi nodes.
- [ ] Mỗi registration có key verification set riêng; North key không thể verify South response.
- [ ] SAMLResponse phải pass XML Signature, issuer, audience, recipient, destination, InResponseTo, time, replay trước khi tạo Authentication.
- [ ] IdP-initiated unsolicited flows chỉ enabled khi routing/issuer/audience duy nhất và risk approved.
- [ ] Cross-tenant user identity map bằng `(issuer, stable subject)`, không chỉ email/name.
- [ ] Business role/tenant/resource authorization độc lập với SAML trust, không cấp quyền chỉ vì login thành công.
- [ ] SP metadata endpoints trả đúng entityID/ACS/public signing/encryption cert cho từng registration và scheme HTTPS.
- [ ] Signed fixtures thật cho N1/N2/S1, including invalid issuer/audience/recipient and signed metadata negative.
- [ ] Test cache TTL±1/validUntil±1 theo clock đã kiểm soát, network outage, invalid new metadata và rollback prevention.
- [ ] Test multi-node stale cache, IdP cutover giữa in-flight AuthnRequest/Response, clustered sessions và rollback theo security.
- [ ] Test SAML SLO behavior, metadata endpoint errors, per registration rotation + unaffected neighbors.
- [ ] Audit ghi metadataGeneration, verified key fingerprints, activation decision, refresh lag, per-pod versions, không log secrets.
- [ ] Có runbook on-call, change approval, owner IdP/SP, freeze window và thước đo hoàn tất rollout.
- [ ] Không giảm signature/issuer/audience/time checks để làm test passing hay cứu login.
- [ ] Sau khi retire key bị lộ/không còn dùng, kiểm **negative old-key acceptance** là PASS ở mọi pod, không chỉ một request thành công bằng key mới.

**Kết luận:** Kiểm thử SAML2 lifecycle không kết thúc ở việc tải metadata HTTP 200 hoặc một lượt đăng nhập thành công. **Metadata refresh** phải có nguồn đáng tin, time/expiry/atomic activation; **key rotation** phải có overlap được kiểm soát, nhiều certificate được quản lý theo đúng **mục đích và registration**; **multi-registration** phải cô lập issuer, SP EntityID, ACS, keys, session correlation và tenant authorization. Một pipeline an toàn chứng minh cả hai mặt: **đúng đối tác tiếp tục đăng nhập khi chuyển khóa hợp lệ**, còn **metadata giả, khóa lạ, khóa cũ đã thu hồi, Response sai tenant hoặc sai điều kiện SAML luôn bị từ chối**.

## 23. Tài liệu tham khảo

1. [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, multiple asserting parties, metadata lookup, `CachingRelyingPartyRegistrationRepository` và routes.
2. [Spring Security – SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `AssertingPartyMetadataRepository`, `OpenSaml5AssertingPartyMetadataRepository`, metadata signature validation, `saml2Metadata`.
3. [Spring Security – Authenticating SAML 2.0 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): response verification/decryption, assertion validation, registration lookup và custom providers.
4. [Spring Security 6.5 – CachingRelyingPartyRegistrationRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/CachingRelyingPartyRegistrationRepository.html): caching, loader và `setCache` semantics.
5. [Spring Security 6.5 – RelyingPartyRegistration API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html): SP/AP pair, EntityIDs, ACS, signing/decryption credentials.
6. [Spring Boot – SAML 2.0 Relying Party Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): multiple registrations và Spring Boot YAML credentials.
7. [Spring Security – SAML 2.0 Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): AuthnRequest signing, bindings và metadata.
8. [OASIS – SAML V2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `EntityDescriptor`, `KeyDescriptor`, `validUntil`/`cacheDuration`.
9. [OASIS – SAML V2.0 Core Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Response, Assertion, Signature, issuer, audience, conditions và subject confirmation.
10. [OASIS – SAML V2.0 Bindings Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-POST/Redirect bindings, signature and RelayState.
11. [OASIS – SAML V2.0 Errata05, metadata caching/validity clarification](https://docs.oasis-open.org/security/saml/v2.0/errata05/csprd01/saml-v2.0-errata05-csprd01.html): phân biệt cacheDuration và validUntil.
12. [OWASP – SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): XML signatures, trust configuration và signed-node verification.
13. [OWASP – SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): URL allowlist và external metadata fetch.
14. [OWASP – XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): metadata XML parser hardening.
15. [OWASP – Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): HTTPS PKIX/trust/hostname verification.
16. [Java 17 – AtomicReference API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): atomic snapshot publication trong Java 17 demo.
