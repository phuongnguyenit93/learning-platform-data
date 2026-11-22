# Quản lý thay đổi metadata và luân chuyển khóa độc lập cho từng tenant trong SAML 2.0

> **Chủ đề:** Spring Security – federation · **Nhóm:** Nhiều IdP và tenant. Bài học tập trung vào vận hành **nhiều SAML Identity Provider (IdP)** trong một Service Provider (SP) Spring Security: lấy và xác minh metadata, phát hiện thay đổi, bảo vệ biên tin cậy của từng tenant, luân chuyển certificate/khóa của IdP và SP theo lịch **độc lập**, công bố/cập nhật metadata an toàn, triển khai nguyên tử nhiều nút, rollback, monitoring và kiểm thử âm tính. Ví dụ chủ yếu dùng Spring Boot 3.x / Spring Security 6.x Servlet; chỗ nào API phụ thuộc version đều được chỉ rõ. Ví dụ Java thuần chạy được bằng JDK 17+.

## 1. Bài toán thực tế: mỗi tenant có lịch IdP và key riêng

Một ứng dụng B2B SaaS là SAML **Service Provider** cho nhiều khách hàng doanh nghiệp. Mỗi khách hàng là một **tenant** và có thể dùng một IdP riêng:

| Tenant nội bộ | Registration ID | IdP entityID | IdP SSO endpoint | Khóa IdP được SP tin |
| --- | --- | --- | --- | --- |
| Công ty A | `tenant-a` | `https://idp-a.example.org/entity` | `https://idp-a.example.org/sso` | `A-old` |
| Công ty B | `tenant-b` | `https://login-b.example.net/issuer` | `https://login-b.example.net/saml/sso` | `B-2026` |
| Công ty C | `tenant-c` | `https://sso-c.example.com/idp` | `https://sso-c.example.com/saml` | `C-current` |

Đây là dữ liệu **giả lập**; tên `A-old`/`B-2026` chỉ là mã key trong bài học, **không phải public-key fingerprint hoặc private key thật**.

Ngày thứ Hai, tenant A chuẩn bị thay IdP signing certificate. Tenant B giữ nguyên; tenant C đổi SingleSignOnService URL sau đợt bảo trì. Nếu ứng dụng có **một bộ khóa chung**, một cache metadata toàn cục không tách tenant, hoặc dùng “latest metadata” từ bên ngoài mà không kiểm tra, thay đổi của A có thể làm hỏng hoặc giảm an toàn đăng nhập của B/C.

**Mục tiêu thiết kế:** một cập nhật metadata của tenant A chỉ thay đổi **registration A** sau khi được kiểm tra, áp dụng đầy đủ tới các instance phục vụ A; B/C giữ nguyên issuer, endpoint, khóa, policy và session. Mọi SAMLResponse phải được verify bằng **đúng khóa IdP của registration được chọn**.

### Các kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt `registrationId`, `tenantId`, SP entityID và IdP entityID; tránh cross-tenant trust confusion.
2. Đọc `EntityDescriptor`, `IDPSSODescriptor`, `KeyDescriptor`, `SingleSignOnService`, `validUntil` và `cacheDuration`.
3. Thiết kế pipeline **fetch → authenticate metadata → validate policy → stage → approve → publish atomically → monitor → retire** cho từng tenant.
4. Thực hiện **IdP signing-key rollover** bằng giai đoạn chấp nhận old+new, không mở trust cho tenant khác.
5. Phân biệt IdP verification key, SP private signing key, SP private decryption key và **metadata signing trust anchor**.
6. Sử dụng `RelyingPartyRegistrationRepository` và các cấu hình Spring Security SAML2 với version caveat.
7. Kiểm soát thay đổi endpoint, issuer, algorithm, certificate và nhiều SP nodes mà không fail-open.
8. Kiểm thử zero-downtime rotation, rollback, compromised key, in-flight AuthnRequest và cô lập tenant.

## 2. Các định danh cần tách tuyệt đối

| Thành phần | Ai đặt/quản lý? | Ý nghĩa | Có tự đồng nhất với tenant? |
| --- | --- | --- | --- |
| `tenantId` | Ứng dụng SaaS | Ranh giới dữ liệu/quyền và hợp đồng khách hàng | Là ID nội bộ |
| `registrationId` | SP/Spring Security | Khóa tra `RelyingPartyRegistration` | Có thể ánh xạ 1-1, **không bắt buộc** |
| SP `entityId` | SP | Định danh SP xuất hiện làm `Issuer` AuthnRequest, audience nhận SAML | Có thể chung hoặc tách theo tenant; phải nhất quán metadata |
| IdP `entityId` | IdP | `Issuer` của Response/Assertion cần verify | Không được lấy từ raw XML làm source of truth |
| `NameID` | IdP | Định danh subject theo hợp đồng | Không đảm bảo unique giữa mọi IdP/tenant |
| Certificate fingerprint/key ID | SP inventory | Đại diện cho public key/cert đã duyệt | Không thay registration/issuer mapping |

Ví dụ user có email `alice@example.com` ở tenant A và một account khác cùng email ở B. Nếu app map identity chỉ theo email, một assertion hợp lệ của tenant B có thể được dùng nhầm để truy cập data của A. Identity mapping nên có namespace như **(tenantId, IdP issuer/registration, NameID hoặc stable subject key)**; chỉ cấp quyền sau khi trust/claims và tenant relationship đã được xác minh.

**Không** chọn tenant cuối cùng chỉ vì browser gửi query `?tenant=tenant-a` hoặc XML `Issuer` tự khai. Request routing có thể dùng registration ID từ URL để tìm một cấu hình **đã được allowlist**; callback phải ràng buộc với registration/trust, request state và issuer. Khi một IdP phục vụ nhiều tenant, cùng `entityID` có thể xuất hiện ở nhiều registrations; lookup chỉ theo issuer lúc đó **mơ hồ**. Cần cơ chế resolve được thiết kế rõ, không “chọn bản ghi đầu tiên”.

## 3. Metadata SAML2 chứa những gì?

SAML 2.0 metadata là tài liệu XML mô tả **entities, endpoints, bindings, khóa/certificates và yêu cầu chính sách**. Với một IdP có thể có:

- `md:EntityDescriptor entityID=...`: định danh IdP/đối tác.
- `md:IDPSSODescriptor`: role IdP cho SAML SSO.
- `md:KeyDescriptor use="signing"`: public key/certificate để các SP xác minh chữ ký IdP.
- `md:KeyDescriptor use="encryption"`: public key phục vụ encryption theo role/profile; không mặc định thay signing trust.
- `md:SingleSignOnService Binding=... Location=...`: nơi IdP nhận `AuthnRequest`.
- `md:SingleLogoutService`: điểm nhận `LogoutRequest`/`LogoutResponse` nếu hỗ trợ.
- `WantAuthnRequestsSigned`: yêu cầu IdP đối với chữ ký AuthnRequest từ SP.
- `validUntil` và `cacheDuration`: thông tin về thời hạn/caching metadata, **không phải** thời điểm certificate hết hạn hoặc TTL SAML assertion.

### 3.1. Đọc cấu trúc XML

Đoạn sau minh họa **hai signing keys trong giai đoạn rollover**, không phải metadata hợp lệ để đưa vào production vì chuỗi certificate chỉ là dữ liệu giả.

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp-a.example.org/entity"
    validUntil="2026-12-31T00:00:00Z"
    cacheDuration="PT6H">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="true">

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_OLD_TEST_CERT</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_NEW_TEST_CERT</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp-a.example.org/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

Hai `KeyDescriptor use="signing"` là cách mô tả **nhiều public signing keys được chấp nhận ở phía SP** trong giai đoạn IdP đổi key, miễn là metadata mới đã được xác minh đáng tin. Trong metadata thật, `ds:X509Certificate` chứa DER certificate Base64; không copy giá trị giả ở đây.

**Điểm bảo mật quan trọng:** có hai keys trong metadata không có nghĩa tin hai keys bất kỳ do browser gửi. SP chỉ dùng những keys đã có trong registration được admin/metadata trust chain chấp nhận, và chỉ cho IdP tương ứng.

### 3.2. KeyDescriptor không đồng nghĩa metadata signature

`ds:Signature` ký **chính tài liệu metadata** (nếu metadata được ký) là chuyện khác `KeyDescriptor use="signing"` chỉ **khóa dùng ký bản tin SAML Response/Assertion**. Một certificate vừa xuất hiện trong metadata **không tự xác thực nội dung metadata ấy**.

Nếu đang kiểm tra metadata signed, phải có **metadata verification trust anchor đã bootstrap** (ví dụ cert của federation operator/IdP được pin từ kênh quản trị). Đừng làm logic:

```text
Tải metadata mới → lấy certificate mới từ KeyDescriptor
→ dùng ngay certificate đó tin chữ ký của metadata vừa tải
→ chấp nhận mọi thay đổi.
```

Đây là kiểu **trust-on-first-use không kiểm soát**; attacker thay metadata có thể tự đưa khóa của họ vào rồi tự ký tài liệu giả. Muốn rotate metadata-signing trust anchor, phải qua một quy trình phân phối/duyệt ngoài băng hoặc chuỗi trust đã được phê duyệt.

### 3.3. validUntil và cacheDuration không phải một

| Trường | Ý nghĩa | Điều cần làm |
| --- | --- | --- |
| `validUntil` | Hạn trên mà metadata producer tuyên bố metadata còn hợp lệ | Không tiếp tục tin quá hạn ngoài policy đã phê duyệt |
| `cacheDuration` | Khoảng thời gian gợi ý cho caching khi không có thay đổi/giới hạn khác | Lên lịch refresh, vẫn giới hạn bởi validUntil |
| Certificate `NotAfter` | Ngày hết hạn certificate X.509 | Theo dõi riêng; certificate expiration policy trong SAML có nuance |
| Pending `AuthnRequest` TTL | Thời gian login transaction chờ callback | Không đồng nhất với metadata cache |
| SP authenticated session TTL | Thời gian phiên user | Không đồng nhất với metadata hoặc key rollover |

**Nuance:** trong SAML metadata, một certificate X.509 có thể được dùng làm **vật chứa public key**, không mặc định là một PKIX client/server certificate. Metadata interoperability profile có các chi tiết riêng về việc sử dụng metadata key ngay cả khi certificate có đặc tính mà một TLS PKIX verifier sẽ xét khác. Vì vậy chính sách doanh nghiệp có thể yêu cầu kiểm tra `NotBefore/NotAfter` và key usage, nhưng không được coi “PKIX certificate expiry = SAML metadata validity” là đẳng thức của tiêu chuẩn. Quan trọng hơn: **trust đến từ metadata đã được xác thực và registration policy**, không phải chỉ từ certificate còn hạn.

## 4. Multi-tenant trust boundary trong Spring Security

### 4.1. Mỗi tenant có một registration được tin cậy

`RelyingPartyRegistration` là mô hình Spring Security chứa SP/IdP entityIDs, endpoints, bindings và credentials. `RelyingPartyRegistrationRepository` tra cấu hình bằng `registrationId`. Với nhiều IdP, app cung cấp nhiều registrations:

```text
RelyingPartyRegistrationRepository
  |
  +-- tenant-a
  |     SP entityID / ACS / signing / decryption config A
  |     IdP entityID A
  |     IdP verification certificates A-old, A-new
  |     IdP SSO/SLO endpoints A
  |
  +-- tenant-b
  |     SP entityID / ACS / signing / decryption config B
  |     IdP entityID B
  |     IdP verification certificate B-current
  |     IdP endpoints B
  |
  +-- tenant-c
        ... riêng C
```

Một change event của A phải cập nhật **chỉ cấu hình A**. Không dùng một `List<X509Certificate> allTenantsCertificates` làm nguồn verify cho mọi issuer. Nếu IdP B gửi SAMLResponse với certificate của A, dù chữ ký toán học đúng, kết quả phải **reject cross-tenant trust mismatch**.

### 4.2. Các lookup/routing có thể gây nhầm

- `GET /saml2/authenticate/tenant-a` khởi động login theo registration A.
- `POST /login/saml2/sso/tenant-a` là callback thường gặp. Response filter/converter lấy registration và kiểm tra message thực tế.
- Nếu callback không có registrationId, một số đường resolver dùng issuer hoặc pending request. **Khi IdP entityID không unique, lookup theo issuer đơn độc không đủ**. Cần giữ state/tenant binding và dùng resolver có policy chặt.
- Một browser route `tenant-a` không có quyền tự tải metadata từ URL bất kỳ. Mọi metadata source phải là ID đã được cấu hình/được admin phê duyệt.
- Tenant/role mapping sau SAML authentication không được dựa duy nhất vào `NameID`/email hoặc query người dùng gửi.

Spring Security tài liệu có `RelyingPartyRegistrationResolver` và `RelyingPartyRegistrationRepository` để kiểm soát resolution. Nếu ứng dụng có callback dùng chung hoặc nhiều IdP cùng issuer, hãy test **registration mismatch** và **ambiguous issuer** thay vì dựa vào default inference.

### 4.3. Khác biệt authentication và authorization

Một assertion hợp lệ từ IdP A chỉ chứng minh **IdP A** đã xác thực subject cho SP entityID tương ứng. Nó không tự cho quyền đọc dữ liệu tenant B. Sau login phải gắn principal với **tenant context đã được xác thực** và kiểm tra authorization cho từng resource/object.

Nếu một user có account ở nhiều tenant, switch tenant trong UI phải có policy riêng; không cho request chỉ đổi `tenantId` ở cookie/query để dùng `Authentication` của issuer khác.

## 5. Bốn loại khóa cần luân chuyển độc lập

| Khóa / certificate | Người giữ private key | Bên dùng public key | Tác dụng | Khi rotate |
| --- | --- | --- | --- | --- |
| **IdP SAML signing key** | IdP của tenant A | SP dùng để verify Response/Assertion từ IdP A | Trust inbound login | IdP A publish cert mới → SP A tin old+new → IdP A switch signer → retire old |
| **SP AuthnRequest signing key** | SP, có thể riêng tenant A | IdP A verify signed AuthnRequest | Trust outbound login request | SP publish public cert mới cho IdP A → IdP A trust → SP switch private signer → retire old |
| **SP decryption key** | SP, có thể riêng tenant A | IdP A encrypt assertions tới SP cert A | Bảo mật payload | Publish new decryption cert → IdP A switch encryption → SP giữ old private decrypt cho in-flight messages → retire |
| **Metadata signing key/trust anchor** | IdP hoặc federation metadata signer | SP verify signed metadata | Trust **chính nguồn config** | Phân phối/approve anchor mới trước; không tự tin public key vừa tải |

Đôi khi một SP keypair được sử dụng cho cả signing và decryption theo cấu hình, nhưng **lý do nghiệp vụ, rủi ro và thứ tự rollover của hai mục đích khác nhau**. Nếu hệ thống yêu cầu cô lập tenant mạnh, dùng cặp khóa riêng/secret ACL riêng cho từng tenant là lựa chọn đáng cân nhắc.

**Không nhầm:** cert do IdP A dùng ký SAMLResponse **không** phải SP private key; cert metadata signer có thể khác cert SAML Response signer; cert IdP signing không được đưa vào pool kiểm chứng của tenant B.

## 6. Vòng đời thay đổi metadata theo từng tenant

Một pipeline vận hành nên tách **candidate** khỏi **active**:

```text
Change request for TENANT A
        |
        v
Resolve approved tenant + metadata source
        |
        v
FETCH có timeout, HTTPS và giới hạn XML size/SSRF
        |
        v
VERIFY provenance (signed metadata hoặc kênh quản trị)
        |
        v
VALIDATE: entityID, role, endpoints, keys, algorithms,
          validUntil/cacheDuration, policy & tenant boundaries
        |
        v
DIFF vs active A; classify routine vs high-risk changes
        |
        v
STAGE candidate A vNext (không đổi active)
        |
        v
TEST on isolated environment with signed SAML fixtures
        |
        v
APPROVAL (dual control cho trust/issuer/key changes)
        |
        v
PUBLISH atomically A vNext with expected version
        |
        v
PROPAGATE / observe all nodes, measure login failures
        |
        v
RETIRE old key/metadata after defined grace, or ROLLBACK
```

Không “tải metadata mới rồi replace cả repository” mà chưa kiểm tra thay đổi. **Candidate không hợp lệ phải bị từ chối mà không làm thay đổi active config**. Lưu audit record đủ để giải thích ai đã duyệt, version/digest, thời điểm và tenant, nhưng không log secrets.

### 6.1. Fetch metadata an toàn

- Source URL/file nằm trong **allowlist per tenant**, ví dụ từ tenant onboarding workflow có chứng thực admin.
- Dùng HTTPS/TLS hợp lệ khi lấy online, xác minh hostname/cert của TLS, redirect policy chặt và **không** nhận `?metadataUrl=...` từ end user.
- Chống SSRF: không cho fetch arbitrary host/private-network/link-local/localhost, validate DNS resolution, redirects và endpoints; giới hạn số lần redirect, byte size, timeout, concurrency.
- Parse XML an toàn: cấm external entities/DTD/XXE, entity expansion, remote schema/reference fetching, giới hạn độ sâu/size, dùng parser đã được maintain.
- Nếu metadata được ký, xác minh chữ ký bằng **bootstrap trust anchor** phù hợp; không tự dùng ký mới trong tài liệu để chứng minh tài liệu đó đáng tin.
- Nếu metadata **không ký**, riêng HTTPS chỉ bảo vệ kết nối đến một endpoint đang được trust; governance vẫn cần đảm bảo source/authority đúng, phê duyệt thay đổi nhạy cảm và giới hạn phạm vi.
- Một `EntitiesDescriptor` có thể chứa nhiều IdPs; chỉ lấy entity có `entityID` đã được tenant cấu hình, không tự chọn “entity đầu tiên” hoặc một issuer tương tự.
- Sau parse, kiểm tra `validUntil`/`cacheDuration` và sự tương thích với cache policy; không dùng thời hạn session làm thay metadata freshness.

### 6.2. Phân loại thay đổi thay vì auto-accept mọi diff

| Diff | Mức độ xử lý đề xuất | Lý do |
| --- | --- | --- |
| Thêm `KeyDescriptor use=signing` cho đúng IdP entityID với provenance hợp lệ | **Key rollover có kiểm soát** | Có thể là pre-publish key mới |
| Loại signing key cũ đã hết thời gian grace | Planned retirement | Có thể làm callback in-flight fail nếu loại sớm |
| Đổi SSO endpoint cùng IdP issuer | Coordinated change + integration test | Redirect mới, trust/endpoint allowlist cần đúng |
| Đổi SLO endpoint/binding | Coordinated SLO test | Có thể ảnh hưởng logout flows riêng |
| Đổi `WantAuthnRequestsSigned`/algorithm suite | Configuration/security review | SP signing credentials và IdP expectations phải hợp nhau |
| Thay IdP `entityID` | **High-risk identity change** | Không phải update khóa thông thường; ảnh hưởng trust/account namespace |
| Xuất hiện certificate của tenant khác | **Reject / investigation** | Trust isolation violation |
| Metadata signature invalid hoặc source URL không đúng | **Reject** | Không có provenance đáng tin |
| `validUntil` đã qua hoặc metadata không còn hợp lệ | Reject candidate; xử lý vận hành | Không cho stale data tự mở trust |
| Dấu hiệu khóa bị compromise | Emergency revoke | Không giữ old+new grace như routine rollover |
| Chỉ đổi contact/organization fields | Low-risk theo governance | Không làm thay đổi authentication trust; vẫn cần verify metadata |

**Đừng dùng hash của file khác để suy rằng “metadata mới an toàn”.** Hash/file digest phục vụ nhận biết thay đổi/versioning, không chứng minh nguồn tin cậy. Chữ ký metadata hoặc kênh quản trị được kiểm tra mới liên quan authenticity.

### 6.3. Validated snapshot bất biến

Mỗi registration active nên gắn với immutable version/snapshot:

```text
tenant-a / registrationId=tenant-a
  revision: 42
  metadata-source: approved IdP A endpoint
  fetched-at: 2026-11-07T04:00:00Z
  valid-until: 2026-12-31T00:00:00Z
  metadata-digest: SHA-256 of authenticated document
  entityID: https://idp-a.example.org/entity
  trust-verification-keys: [A-old, A-new]
  SP-signing-key-version: A-SP-2026
  SSO-endpoint: https://idp-a.example.org/sso
  status: ACTIVE
```

Thông tin trên chỉ là **schema minh họa**; `metadata-digest` không được dùng làm substitute cho signature. Không log raw certificate/private key, toàn bộ XML SAMLResponse hoặc secret RelayState. Audit có thể giữ fingerprint của **public** certificate và encrypted storage references theo policy.

Khi publish A revision 43, cập nhật atomic bản ghi A; B/C vẫn giữ version cũ của chính mình. Phải có **optimistic locking/expected revision** để tránh hai admin hoặc hai job refresh ghi đè lẫn nhau. Với multi-pod, version phải được phân phối nhất quán hoặc sử dụng shared store có khả năng transaction thích hợp.

## 7. IdP signing-key rollover không gián đoạn đăng nhập

### 7.1. Quy trình old + new cho tenant A

Giả định ban đầu SP chỉ tin `A-old`:

| Thời điểm | IdP A thực sự ký Response | SP A chấp nhận keys | Hành động |
| --- | --- | --- | --- |
| T0 | A-old | A-old | Baseline, login bình thường |
| T1: pre-publish | A-old | **A-old và A-new** | Metadata IdP được xác thực chứa cert mới; SP stage/approve/deploy |
| T2: switch signer | **A-new** | A-old và A-new | IdP đổi private signing key sau khi xác nhận SP đã nhận key mới |
| T3: ổn định | A-new | A-old và A-new | Monitor signing failures; chờ callback in-flight/replication |
| T4: retire | A-new | **Chỉ A-new** | Gỡ A-old sau thời gian grace/policy |
| B ở mọi thời điểm | B-current | **Chỉ B-current** | Không thay đổi do A rotate |

Điều kiện để T2 an toàn: **tất cả active SP instances phục vụ tenant A đã tin A-new**, bao gồm pods ở region khác; không chỉ dashboard của một node báo cập nhật. Nếu IdP switch quá sớm, callback từ A-new tới pod còn trust A-old sẽ fail.

### 7.2. Vì sao cần overlap?

IdP A có thể phát SAMLResponse cho một AuthnRequest đang chờ khi SP mới bắt đầu rollout. Nếu SP retire A-old ngay khi thấy A-new, những response IdP đã ký bằng A-old nhưng chưa đến ACS có thể bị reject. Overlap cho phép hai keys **của cùng IdP A** trong một cửa sổ có giới hạn.

**Không tự kéo dài overlap vô hạn**. Quy định grace dựa trên SAML response lifetime, pending request TTL, rollout completion, IdP timing và audit; retire old khi có bằng chứng migration đã xong.

**Ngoại lệ đặc biệt:** nếu A-old bị compromise, **không tiếp tục tin A-old chỉ để giữ zero downtime**. Revoke/gỡ key bị lộ theo incident response, chấp nhận phải re-login hoặc tạm gián đoạn thay vì tiếp tục chấp nhận assertion giả.

### 7.3. Một signing cert có thể có nhiều nơi tham chiếu

Kiểm tra KeyDescriptor `use="signing"` theo role IdP và metadata trust. Chỉ cập nhật **IdP verification credentials** trong `RelyingPartyRegistration` A; không tự update:

- SP private signing key dùng phát AuthnRequest.
- SP private decryption key dùng giải `EncryptedAssertion`.
- Signing keys của tenant B/C.
- Metadata signing trust anchor.

Một certificate có thể chứa public key cùng subject/issuer name nhưng vẫn phải kiểm tra **đúng key/certificate identity**; không tin chỉ vì common name giống.

## 8. SP signing-key rotation theo từng tenant

Nếu SP ký `AuthnRequest` cho IdP A:

```text
SP A private signing key (old/new)
      |
      +--> ký AuthnRequest
                    |
IdP A trust SP public signing certificate(s) từ metadata/contract
```

Quy trình khác IdP inbound key rotation:

1. SP tạo keypair mới `A-SP-new` trong HSM/secret manager; public cert được chuẩn bị.
2. SP publish **new SP signing certificate** trong SP metadata cho registration A hoặc đưa qua kênh IdP A chấp nhận, giữ old public cert trong khoảng chuyển tiếp nếu IdP hỗ trợ.
3. Đợi IdP A xác nhận đã trust new certificate ở **mọi node** nhận AuthnRequest.
4. SP bắt đầu ký **request mới** bằng new private key; giám sát IdP từ chối “invalid AuthnRequest signature”.
5. Sau khi request cũ không còn cần kiểm tra và IdP A chuyển xong, retire old trust/private key theo policy.
6. B/C không bị thay key/metadata nếu yêu cầu là độc lập tenant.

**Không đảo thứ tự:** nếu SP bắt đầu ký new trước khi IdP đã trust new public certificate, login A sẽ bị từ chối.

Trong một số hệ thống SP chung entityID/keypair cho nhiều tenants, luân chuyển **hoàn toàn độc lập** không có ngay từ kiến trúc. Phải quyết định tách SP entityID/registration/cert tương ứng và đăng ký lại với IdP; không tuyên bố có tenant isolation nếu dùng chung private key có blast radius trên mọi tenant.

## 9. SP decryption-key rotation cũng khác signing rotation

Nếu IdP A phát `EncryptedAssertion` được mã hóa cho SP public encryption certificate:

1. SP A tạo private/public encryption keypair mới; giữ **old private decryption key** để giải những assertions đang trên đường.
2. SP A publish new **public encryption cert** cho IdP A (metadata/contract).
3. IdP A bắt đầu encrypt với new cert **sau khi** SP A có thể decrypt bằng new private key.
4. Trong thời gian overlap, SP giữ old+new private decryption credentials theo policy, vì có thể vẫn gặp ciphertext dùng old key.
5. Khi không còn ciphertext in-flight và IdP xác nhận migration, loại old private key.
6. Tách quyền đọc old/new decryption secrets giữa tenants và giữ rotation audit.

**Không nhầm:** SP private decryption key không phải IdP public signing cert. Một IdP signing rollover không cần đổi SP private decryption key trừ khi có lý do/contract riêng.

## 10. Metadata-signing trust anchor rotation: vấn đề bootstrap trust

Đây là phần dễ bị bỏ qua nhất trong hệ thống tự động refresh metadata.

### 10.1. Trusted metadata khác trusted SAML Response

Một tổ chức có thể công bố metadata được ký bởi **metadata signer**. SP cần một anchor ban đầu được giao qua kênh quản trị để kiểm tra chữ ký của metadata. Sau khi metadata được xác thực, SP mới có thể tiếp nhận `KeyDescriptor` chứa keys IdP dùng ký SAMLResponse.

**Luân chuyển anchor metadata** không được thực hiện chỉ bằng cách: “metadata tải về có cert mới nên dùng cert đó tin metadata”. Nếu làm vậy, attacker có thể tạo metadata giả và tự ký.

### 10.2. Quy trình anchor rollover

1. Admin hoặc federation authority công bố metadata signer new cert qua kênh **đã được xác thực** (signed notice/secure admin workflow).
2. SP đưa new metadata verification cert vào trust list của **đúng nguồn metadata tenant A** theo approval/versioning.
3. Trong giai đoạn overlap, signed metadata có thể dùng old hoặc new signer theo chính sách.
4. Metadata producer chuyển sang ký bằng new private key, SP xác minh thành công.
5. Sau cutoff, gỡ old metadata trust anchor khỏi nguồn A.
6. Nếu old signer compromise, thu hồi ngay, kiểm tra metadata lịch sử và mọi registration chịu ảnh hưởng.

Một IdP có thể dùng chung signer metadata cho nhiều customers; trong tình huống này thay metadata trust anchor có blast radius rộng hơn từng tenant và phải được governance ở **đúng phạm vi signer thật**, không giả vờ mỗi tenant có key độc lập nếu dùng chung một federation signature key.

### 10.3. Ghi chú Spring Security/OpenSAML theo phiên bản

Spring Security documentation mới có `OpenSaml5AssertingPartyMetadataRepository`, với `verificationCredentials(...)` để xác minh **metadata signatures**. Tài liệu chính thức lưu ý: nếu không cung cấp metadata verification credentials, component này **không thực hiện metadata signature validation**. Đó là trạng thái phải hiểu rõ, không coi HTTPS endpoint tự động tương đương signed metadata.

API này thuộc các phiên bản dùng OpenSAML 5; Spring Security 6.3/6.4 và các bản dùng OpenSAML 4 có thể có đường xây metadata khác. Hãy tra **javadoc/release đang chạy**. Không copy class OpenSAML 5 vào project 6.3 rồi hạ bảo mật để tránh compile error.

Dù có auto-refresh, **automatic metadata retrieval không tự bảo đảm authentication/provenance**, không tự thay approval workflow hoặc kiểm tra entityID/tenant trust.

## 11. Spring Security: cấu hình nhiều registrations cơ bản

### 11.1. YAML cho hai tenant

Một ứng dụng Spring Boot 3.x có thể khai báo hai registrations riêng, mỗi tenant có metadata IdP từ file admin đã kiểm tra:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          tenant-a:
            entity-id: "{baseUrl}/saml/sp/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/tenant-a-sp-signing.key"
                  certificate-location: "file:/run/config/tenant-a-sp-signing.crt"
            assertingparty:
              metadata-uri: "classpath:saml/tenant-a-idp.xml"
          tenant-b:
            entity-id: "{baseUrl}/saml/sp/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/tenant-b-sp-signing.key"
                  certificate-location: "file:/run/config/tenant-b-sp-signing.crt"
            assertingparty:
              metadata-uri: "classpath:saml/tenant-b-idp.xml"
```

**Điều kiện:** `tenant-a-idp.xml` và `tenant-b-idp.xml` đã được xác thực/quản trị đúng nguồn; SP public entityID/ACS phù hợp các IdP, có signing credentials và IdP trust. Đây là **static configuration example**, không tự refresh file/metadata mới giữa lúc app chạy.

Đường `classpath:...` giúp tránh auto fetch arbitrary web URL ở startup, nhưng **không tự chứng minh metadata được ký hoặc đã được admin duyệt**. Pipeline build/deploy phải phân phối files đã được xác minh và tách tenant. Key files ở `/run/secrets` chỉ là đường dẫn giả, cần secret manager/ACL thực tế.

### 11.2. SecurityFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiTenantSamlSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là **Spring configuration class**, không thể chạy riêng bằng `java MultiTenantSamlSecurity`. Với `RelyingPartyRegistrationRepository` có registrations A/B, browser có thể vào:

```text
GET /saml2/authenticate/tenant-a
GET /saml2/authenticate/tenant-b
```

Mỗi URL cần tạo AuthnRequest với IdP/SP metadata của **đúng registration**. Callback `POST /login/saml2/sso/{registrationId}` cần verify issuer/signature/audience/state theo trust registration tương ứng. Không tạo one-size-fits-all verifier dùng union public keys của mọi tenant.

### 11.3. Tạo repository từ metadata đã kiểm tra

Khi cần code thay vì YAML, API Spring Security 6.x có builder `RelyingPartyRegistrations.fromMetadataLocation(...)`. Ví dụ class **Spring config** với metadata XML ở classpath:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration
        .InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrations;

@Configuration
public class TenantRegistrationConfiguration {

    @Bean
    RelyingPartyRegistrationRepository samlRegistrations() {
        RelyingPartyRegistration tenantA = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/tenant-a-idp.xml")
            .registrationId("tenant-a")
            .build();
        RelyingPartyRegistration tenantB = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/tenant-b-idp.xml")
            .registrationId("tenant-b")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(
            tenantA, tenantB);
    }
}
```

**Giới hạn quan trọng:**

- Các file metadata phải được **xác thực và validate trước** khi đưa vào classpath. `fromMetadataLocation` là hàm xây registration, không phải cơ chế approval/metadata signature trust toàn diện.
- Builder minh họa chỉ lấy settings từ IdP metadata. Nếu IdP yêu cầu signed AuthnRequests, cần bổ sung **SP private signing credential** cho từng registration; nếu IdP yêu cầu encrypted assertion, cần SP decryption credentials.
- Tránh khai báo bean này **cùng** auto-configured Boot registration YAML mà không hiểu bean override. Chọn **một nguồn registration chính**.
- `InMemoryRelyingPartyRegistrationRepository` được dựng ở thời điểm tạo bean, **không có pipeline live rotation** chỉ vì file classpath thay đổi. Muốn dynamic update cần reload/rebuild/repository/caching architecture và điều phối version.
- Khi SP cùng IdP có issuer trùng giữa nhiều registrations, cấu hình callback resolver/state phải đảm bảo không nhầm tenant.

### 11.4. CachingRelyingPartyRegistrationRepository và auto refresh

Theo Spring Security API, `CachingRelyingPartyRegistrationRepository` xuất hiện từ **6.4**. Nó là wrapper **lazily load và cache** một `IterableRelyingPartyRegistrationRepository` từ một loader, hỗ trợ `setCache(...)` dùng Spring Cache. Cache mặc định là **ConcurrentMapCache** không tự expire. Do đó:

- `setCache` với Redis/Cache backend có TTL/invalidation phù hợp có thể tham gia giải quyết refresh và chia sẻ state.
- **Cache TTL không tự kiểm tra metadata signature**, entityID và tenant policy.
- Cache shared không đủ nếu mỗi pod build registration khác nhau hoặc revision chưa được phát đồng bộ.
- Nếu cần đổi **chỉ tenant A**, nên chọn thiết kế per-tenant config/revision và invalidate/publish đúng tenant hoặc snapshot; đừng đột ngột refresh toàn repository bằng metadata chưa kiểm tra.
- Không dùng class này trong Spring Security 6.3 nếu version không có; không mặc định API của Spring Security 7.x tương thích 6.x.
- Khi loader fetch metadata online, không chạy tự do trên request path với network wait/SSRF risk; nên kiểm tra metadata vào staging/control plane rồi publish đến runtime.

Tài liệu Spring Security mới có thêm các metadata repository bằng OpenSAML 5 với refresh/validation capabilities. **Chọn đúng API theo release và test** chứ không gán trách nhiệm refresh/signature/atomic update cho một class không có contract ấy.

## 12. Cấu trúc control plane và data plane

### 12.1. Tách quản trị metadata khỏi luồng login

Thiết kế nên có hai mặt phẳng:

```text
CONTROL PLANE
  Approved tenant IdP metadata sources
        |
  Fetch + authenticate + validate + diff + approval
        |
  Versioned tenant configs (A:v43, B:v8, C:v15)
        |
  Publish/canary/rollback + audit
        |
        v
DATA PLANE (Spring Security SP instances)
  POD 1 -- local validated snapshots/cache
  POD 2 -- local validated snapshots/cache
  POD 3 -- local validated snapshots/cache
        |
  AuthnRequest generation + SAMLResponse verification
```

Login request **không nên phụ thuộc trực tiếp** vào một live HTTP fetch tới metadata URL của IdP ở mỗi lần đăng nhập. Một IdP metadata outage/timeout không được khiến mỗi SP request block vô hạn, cũng không được dẫn tới trust fallback bừa bãi.

Control plane tải/duyệt/đánh version; data plane chỉ sử dụng **active validated snapshot**. Nếu cần auto refresh, candidate luôn phải qua validation gates trước khi thành active.

### 12.2. Versioned update và optimistic concurrency

Giả sử:

```text
Active:
  tenant-a: revision 42, trust=[A-old]
  tenant-b: revision 8,  trust=[B-current]

Admin X chuẩn bị tenant-a revision 43: trust=[A-old,A-new].
Job Y cũng bắt đầu từ revision 42.

Publish X chỉ thành công nếu expectedRevision=42.
Sau khi X publish, tenant-a revision=43.
Publish Y expectedRevision=42 phải bị conflict.
Tenant-b vẫn revision=8.
```

Không dùng một mutable global `HashMap` nhiều thread với `clear()/putAll()`: login trong lúc update có thể thấy một snapshot thiếu credentials hoặc trộn issuer cũ với SSO URL mới. Dùng **immutable snapshot + atomic swap** theo tenant hoặc config store có transaction/version gating.

### 12.3. Multi-pod rollout

Một control-plane commit thành công không đồng nghĩa tất cả pods đã thấy key mới. Trước IdP signer cutover, cần theo dõi:

- Desired revision theo tenant.
- Applied revision/health theo từng pod/region.
- Smoke-test signed fixture với new key ở mỗi deployment cluster.
- Cache invalidation/refresh interval và thời hạn metadata (validUntil).
- Drift alert khi một pod A còn revision cũ.
- Ràng buộc in-flight requests: SAMLResponse cho request do pod A tạo có thể về pod B sau update, cần repository và trust overlap phù hợp.
- Rollback về **last-known-good trusted revision** chỉ khi không tái kích hoạt revoked/compromised key.

Nếu cache eventual-consistency gây window lệch phiên bản, **không** tự cho signature validation thất bại trở thành success. Có thể tạm ngừng cutover cho đến khi rollout đủ an toàn.

## 13. Java 17: registry đa tenant có revision và key rotation độc lập

Ví dụ sau chạy được với **Java 17 thuần**. Nó mô phỏng **định danh signing key đã được trust** bằng strings `A-old`, `A-new`, `B-current` và dùng immutable `Map` cùng `AtomicReference` để publish atomically per tenant. Một cập nhật được phép **chỉ khi expected revision khớp**; các tenant khác không đổi.

**Rất quan trọng:** chương trình **không** tải/parse metadata XML, không giải mã certificate, không kiểm tra chữ ký cryptographic/SAML. Hàm `accepts` chỉ mô phỏng **sự khớp issuer và key label trong registry đã được trust**. Production phải verify signature bằng Spring Security/OpenSAML với public certificates thật và toàn bộ protocol conditions.

Lưu file `TenantMetadataRotationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

public class TenantMetadataRotationDemo {

    record TenantTrust(
            String registrationId,
            String idpIssuer,
            long revision,
            Set<String> acceptedSigningKeys) {

        TenantTrust {
            acceptedSigningKeys = Set.copyOf(acceptedSigningKeys);
        }
    }

    static final class Registry {
        private final AtomicReference<Map<String, TenantTrust>> active;

        Registry(Map<String, TenantTrust> initial) {
            this.active = new AtomicReference<>(Map.copyOf(initial));
        }

        boolean accepts(String registrationId,
                        String issuer, String signingKeyLabel) {
            TenantTrust t = active.get().get(registrationId);
            return t != null
                    && t.idpIssuer().equals(issuer)
                    && t.acceptedSigningKeys().contains(signingKeyLabel);
        }

        boolean rotate(String registrationId,
                       long expectedRevision,
                       Set<String> nextTrustedKeys) {
            if (nextTrustedKeys == null || nextTrustedKeys.isEmpty()) {
                return false;
            }

            while (true) {
                Map<String, TenantTrust> oldSnapshot = active.get();
                TenantTrust existing = oldSnapshot.get(registrationId);

                if (existing == null
                        || existing.revision() != expectedRevision) {
                    return false;
                }

                TenantTrust updated = new TenantTrust(
                    existing.registrationId(),
                    existing.idpIssuer(),
                    existing.revision() + 1,
                    nextTrustedKeys);

                Map<String, TenantTrust> copy =
                        new HashMap<>(oldSnapshot);
                copy.put(registrationId, updated);

                if (active.compareAndSet(
                        oldSnapshot, Map.copyOf(copy))) {
                    return true;
                }
            }
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry(Map.of(
            "tenant-a", new TenantTrust(
                "tenant-a", "https://idp-a.example.org/entity",
                42, Set.of("A-old")),
            "tenant-b", new TenantTrust(
                "tenant-b", "https://login-b.example.net/issuer",
                8, Set.of("B-current"))
        ));

        System.out.println("A old initially: " + registry.accepts(
            "tenant-a", "https://idp-a.example.org/entity", "A-old"));

        System.out.println("A overlap published: " + registry.rotate(
            "tenant-a", 42, Set.of("A-old", "A-new")));

        System.out.println("A new accepted: " + registry.accepts(
            "tenant-a", "https://idp-a.example.org/entity", "A-new"));

        System.out.println("B rejects A key: " + registry.accepts(
            "tenant-b", "https://login-b.example.net/issuer", "A-new"));

        System.out.println("B old unaffected: " + registry.accepts(
            "tenant-b", "https://login-b.example.net/issuer", "B-current"));

        System.out.println("Stale A revision rejected: " + registry.rotate(
            "tenant-a", 42, Set.of("A-new")));

        System.out.println("A old retired: " + registry.rotate(
            "tenant-a", 43, Set.of("A-new")));

        System.out.println("A old after retirement: " + registry.accepts(
            "tenant-a", "https://idp-a.example.org/entity", "A-old"));

        System.out.println("A new after retirement: " + registry.accepts(
            "tenant-a", "https://idp-a.example.org/entity", "A-new"));
    }
}
```

Chạy với JDK 17+:

```bash
javac TenantMetadataRotationDemo.java
java TenantMetadataRotationDemo
```

Stdout **chính xác**:

```text
A old initially: true
A overlap published: true
A new accepted: true
B rejects A key: false
B old unaffected: true
Stale A revision rejected: false
A old retired: true
A old after retirement: false
A new after retirement: true
```

### 13.1. Giải thích kết quả

- Ban đầu tenant A tin `A-old` ở revision 42.
- Lệnh `rotate("tenant-a", 42, {A-old,A-new})` tạo revision 43, duy trì overlap; ứng dụng có thể chấp nhận new key cho **A** nếu metadata/trust đã được control plane xác minh.
- Tenant B vẫn chỉ tin `B-current`, không chấp nhận key A dù cùng thuật toán chữ ký.
- Một job bắt đầu từ revision 42 không được ghi đè revision 43; `Stale A revision rejected=false`.
- Khi IdP A hoàn tất switch, revision 44 chỉ giữ `A-new`, loại `A-old`.
- `AtomicReference.compareAndSet` bảo đảm swap snapshot nguyên tử **trong JVM của demo**; nó không phân phối dữ liệu giữa pods hay cung cấp CAS transaction trên Redis.
- `Set.copyOf`/`Map.copyOf` giúp giữ snapshot bất biến; nhưng **không tự kiểm chứng nguồn/issuer/chữ ký SAML**.

**Tuyệt đối không dùng `accepts(...)` thay signature verification production:** attacker có thể tự khai `signingKeyLabel="A-new"`. Trong hệ thống thật phải verify **chữ ký trên đúng signed Response/Assertion** bằng public key IdP của registration A, kiểm tra issuer/audience/destination/recipient/time/InResponseTo và mapping tenant. Demo chỉ thể hiện điều kiện tách trust/phiên bản.

### 13.2. Những gì còn thiếu để dùng trong hệ thống thật

Một production implementation cần:

1. Metadata fetcher đã khóa nguồn, signed metadata verification/approval và XML parser hardening.
2. Từ cert PEM/DER thật xây `Saml2X509Credential.verification(...)` cho đúng IdP registration.
3. Transactional config store và phân phối snapshots theo tenant giữa SP nodes, không chỉ `AtomicReference` local.
4. Rebuild `RelyingPartyRegistration` A toàn bộ một cách nhất quán: issuer/endpoints/bindings/credentials/algorithm policy.
5. Trường metadata signer khác IdP signing key được lưu tách để không tự xác thực metadata bằng nội dung metadata.
6. Grace windows, emergency key revocation, last-known-good version/rollback và quan sát drift.
7. Tích hợp Spring Security request/response filters/provider theo phiên bản, không code custom trust bypass.
8. Bảo vệ key material bằng secret store/HSM và quyền tối thiểu; không lưu private key trong registry demo.

## 14. Biến các bản ghi metadata thành cấu hình Spring Security

Khi cập nhật tenant A:

```text
Verified candidate metadata for tenant-a v43
  |
  +-- ensure entityID still https://idp-a.example.org/entity
  +-- validate SSO/SLO endpoints/bindings and allowed hosts
  +-- extract IDPSSODescriptor signing certificates
  +-- ensure key strengths/algorithms per A policy
  +-- create versioned RelyingPartyRegistration for tenant-a
  +-- preserve SP A signing/decryption credentials unless separately rotated
  |
  v
Publish A v43 atomically into registration repository
  |
  +-- tenant-b registration unchanged
  +-- existing sessions not automatically remapped to B
  +-- in-flight requests handled by overlap/state policy
```

Dùng builder/metadata API đã được Spring Security hỗ trợ thay vì tự parse SAMLResponse hay tự thay signing key theo một header. Nếu sử dụng store động, chỉ **validated configuration** được phép vào live repository. Rebuild toàn bộ registration giúp tránh cấu hình lai “issuer cũ + endpoint mới + cert thiếu” trong một object mutable.

### 14.1. Tránh partial update

Một cập nhật có thể thay nhiều trường:

- IdP entityID/SSO URL.
- IdP `verificationX509Credentials`.
- SLO endpoints/binding.
- `wantAuthnRequestsSigned` và algorithm metadata.
- SP entityID/ACS metadata khi hai bên đồng bộ hợp đồng.

Không áp dụng từng field trực tiếp vào một object đang được các request đồng thời sử dụng. **Atomic snapshot per tenant** bảo đảm một request đọc một bộ cấu hình nhất quán. Nếu đăng nhập bắt đầu ở version cũ nhưng callback đến version mới, phải có overlap/correlation hợp lý, không “thử tất cả keys của mọi tenant” để làm response pass.

### 14.2. Không ghi đè trust config bằng IdP payload

IdP có thể đính kèm `ds:KeyInfo` hoặc self-described issuer trong SAMLResponse. Những thông tin ấy **không** là candidate metadata đã được phê duyệt. Không tự cập nhật `RelyingPartyRegistrationRepository` từ SAMLResponse của browser, không cho user tự set certificate qua login form.

## 15. Cache, refresh, last-known-good và TTL

### 15.1. Hai cache khác nhau

| Cache/store | Dữ liệu | Rủi ro |
| --- | --- | --- |
| **Active tenant registration cache** | RelyingPartyRegistration/verified IdP metadata | Stale trust, sai IdP keys/endpoints, drift giữa nodes |
| **SAML pending AuthnRequest repository** | ID/RelayState/context của login đang chờ | Mất `InResponseTo`, login failure/injection nếu browser binding yếu |
| **Replay cache** | SAML Response/Assertion IDs đã xử lý | Replay across pods nếu local-only |
| **HttpSession store** | Browser session/SecurityContext | Mất authentication state khi callback vào node khác |

Metadata cache TTL không thay logout/session TTL hay replay window; Redis dùng chung không có nghĩa mọi kiểu record được quản lý giống nhau.

### 15.2. Last-known-good phải có hạn và nguồn gốc

Nếu IdP A metadata endpoint tạm lỗi mạng:

- Không tự thay active A bằng metadata trống hoặc chưa verify.
- Có thể tiếp tục dùng **last-known-good authenticated config** trong khoảng mà `validUntil` và **stale-use policy** cho phép; đây là lựa chọn availability có threat review, không phải quyền bỏ qua hết hạn tùy tiện.
- Khi metadata đã thực sự quá hạn hoặc key compromise được xác nhận, phải fail closed theo chính sách, ngay cả khi làm gián đoạn SSO A.
- Tenant B/C tiếp tục dùng active snapshots của họ nếu vẫn hợp lệ.
- Báo alert về A fetch failure, time-to-validUntil, key rollover window và số pods version lệch.

### 15.3. Không tin “cacheDuration=PT6H” là SLA tuyệt đối

`cacheDuration` là metadata caching hint theo SAML spec, không cam kết IdP sẽ chỉ đổi key sau sáu giờ hoặc cert sẽ còn hạn sáu giờ. Cần thỏa thuận **key rollover advance notice**, refresh schedule và propagation deadline riêng. `validUntil` còn hiệu lực không có nghĩa **không thể** có key compromise cần revoke ngay.

Tách fetch interval, cache TTL, maximum stale grace, manual revoke push, in-flight SAML request TTL và incident response thresholds.

## 16. Security threat model cho metadata/rotation đa tenant

| Nguy cơ | Cách tấn công/lỗi | Phòng vệ |
| --- | --- | --- |
| Metadata substitution | Attacker đổi file/URL metadata A, thêm key của họ | Authenticated source/metadata signature, approved bootstrap trust, staged validation |
| SSRF / XML external entities | Arbitrary metadata URL/DTD/XML refs | URL allowlist, network egress policy, XML parser hardening và limits |
| Cross-tenant key trust | Key A được thêm vào allowlist B | Per-registration verification credentials + negative tests |
| Tenant confusion | Callback A được resolve thành B vì issuer trùng/URL thiếu registration | Request/tenant binding, explicit registration selection, reject ambiguity |
| Key rollover too early | IdP switch A-new trước khi tất cả SP nodes trust | Pre-publish, readiness gate, rollout dashboard |
| Old key never retired | A-old được trust mãi sau migration | Time-boxed overlap, signed change ticket, retire plan |
| Compromised old key kept for overlap | Attacker ký SAML assertions bằng A-old | Emergency revoke, invalidate impacted sessions, no grace |
| Key type/algorithm downgrade | Metadata mới đòi RSA-SHA1/weak key | Explicit signature/key-strength allowlist, reject unsupported |
| SP signing key leaked | Attacker ký AuthnRequest như SP | HSM/secret ACL/rotation, incident response và IdP trust update |
| SP decrypt key leaked | Assertions bị giải mã ngoài ý muốn | Rotate decryption cert/key, assess data exposure |
| Metadata signing trust hijack | SP tin anchor do untrusted metadata tự đưa | Out-of-band trust bootstrap/approval |
| Cache poisoning/race | Job từ revision cũ ghi đè new tenant config | Immutable versions, CAS/optimistic lock, audit |
| Inconsistent nodes | POD A tin A-new, POD B chưa | Desired/applied version, health checks, rollout guard |
| Replay/correlation bypass | Dùng Response ký thật nhưng sai pending request | Validate `InResponseTo`, audience/recipient/time, replay cache |
| Trust broadening on failure | Retry verify với cert của bất cứ tenant nào | Fail closed, never global fallback |
| Excessive logging | Full assertion/metadata key materials trong traces | Only event IDs/fingerprints public + redaction, protected audit |
| Account collision | Hai tenants có cùng email/NameID | Composite subject namespace + tenant authorization |
| Unapproved endpoint migration | New SSO Location trỏ attacker host | Allowed domain/policy diff + human approval |

**Đặc biệt:** chữ ký RSA-SHA256 hợp lệ của IdP B không được chấp nhận làm danh tính tenant A. **Thuật toán hợp lệ không đồng nghĩa issuer/tenant hợp lệ.**

## 17. Kiểm thử end-to-end khi tenant A rotate

### 17.1. Test functional

| Trường hợp | Kỳ vọng |
| --- | --- |
| A-old ký SAMLResponse ở baseline | SP login tenant A thành công |
| B-current ký SAMLResponse ở baseline | SP login tenant B thành công |
| Publish A-new trong metadata A đã xác thực | Candidate tạo được, không thay active trước approval |
| Sau deploy A overlap, A-old ký response | PASS trong grace của A |
| Sau deploy A overlap, A-new ký response | PASS trong grace của A |
| A-new key được gửi như issuer B | **REJECT** |
| B-current tiếp tục login trong mọi bước A rollout | PASS; B không thay revision/keys |
| IdP A switch sang A-new sau khi mọi pod ready | Login A không gián đoạn |
| A-old bị retire sau grace | A-old bị **REJECT**; A-new vẫn PASS |
| A rollback từ bad endpoint metadata | Chỉ quay về bản trusted A được phép, B/C giữ nguyên |
| Tenant C đổi SSO endpoint độc lập | Test C riêng, không làm đổi A/B |
| A metadata refresh fail tạm thời | Không xóa active A; stale behavior theo policy |
| A metadata đã hết `validUntil` | Không tự nới trust để login pass |
| A signer compromise | Revoke ngay theo incident workflow, không chờ grace |
| Key/cert của IdP A không nằm trong đúng KeyDescriptor | Reject |
| Signed metadata không hợp lệ | Candidate reject, không deploy |
| Certificate rollover trên pod A nhưng pod B chưa nhận | Readiness gate chặn IdP signer cutover |
| User login đang chờ khi key switch | Callback dùng đúng registration/state và accepted overlap keys |

### 17.2. Negative tests về registration/tenant

- Request khởi tạo `/saml2/authenticate/tenant-a`, nhưng response có issuer của B → reject.
- Response signed bằng A-key nhưng audience dành cho SP khác → reject.
- Response signed bằng B-key nhưng issuer khai A → reject.
- Hai tenants chung issuer, callback không có request state rõ → reject ambiguity, không chọn ngẫu nhiên.
- NameID/email giống nhau ở A và B → không cấp resource access chéo tenant.
- Tenant A metadata đổi issuer mà không có approval → candidate reject/high-risk migration.
- URL metadata redirect sang private IP/local network → fetch reject.
- Metadata XML chứa DTD/external entity → parser reject/XXE hardened.
- Metadata file quá lớn hoặc EntityDescriptor nesting bất thường → reject theo limits.
- Candidate có RSA 1024 hoặc SHA-1 signature policy trái yêu cầu → reject.
- Old revoked key còn được gửi sau emergency revoke → reject trên mọi pod.
- Authentication response hợp lệ chữ ký nhưng `InResponseTo` không khớp/expired → reject.
- Metadata cache đã stale và key mới chưa được phân phối → không tự fallback trust từ `KeyInfo`.

### 17.3. Test race và rollback

1. Hai job cùng đọc A revision 42. Chỉ một job được publish revision 43; job còn lại bị version conflict.
2. Publish A revision 43 không làm thay map/snapshot B revision 8.
3. Rollout tới cluster 1 trước cluster 2; IdP A chưa được switch signing key khi cluster 2 chưa ready.
4. Cố inject candidate invalid certificate/issuer; active A vẫn giữ last-known-good.
5. Rollback candidate error chỉ được dùng revision cũ còn **được policy tin**, không khôi phục revoked/compromised key.
6. Trên nhiều pods, callback đến pod khác vẫn verify đúng A key và request state; test signature/digest/audience/correlation thật.
7. Thử concurrent in-flight transactions khi IdP đổi key; xác minh không phá pending request repository hoặc session cookie.

### 17.4. Tiêu chí nghiệm thu

- **Security:** zero acceptance chéo tenant/issuer/key; metadata provenance đã được xác minh; SAML protocol validation không bị bypass.
- **Availability:** key rollover routine không gây login outage khi follow overlap/prepublish, hoặc downtime được dự báo theo contract.
- **Consistency:** desired/applied revision đồng nhất trên các SP nodes trước switch.
- **Isolation:** một lỗi/refresh A không làm B/C đăng nhập thất bại hoặc đổi trust.
- **Observability:** biết tenant nào, revision nào, key status nào nhưng không log raw assertions/private keys.
- **Recovery:** có rollback, revoke emergency, config history, approval audit và alert.

## 18. Dashboard và logging tối thiểu

Một sự kiện metadata update có thể có:

```json
{
  "event": "saml_tenant_metadata_activated",
  "tenant": "tenant-a",
  "registration": "tenant-a",
  "previous_revision": 42,
  "new_revision": 43,
  "change_class": "IDP_SIGNING_KEY_OVERLAP",
  "approval_id": "change-741",
  "result": "ACTIVE",
  "timestamp": "2026-11-07T04:00:00Z"
}
```

Đây là JSON **mẫu giả lập**. Không ghi full `SAMLResponse`, `SAMLRequest`, NameID/email/groups, session cookies, RelayState secrets, private keys hoặc exception chứa XML. Fingerprint của **public** certificate có thể ghi theo policy nếu cần vận hành, nhưng không dùng raw subject/issuer từ payload chưa được trust làm log label.

Monitoring nên theo dõi:

- `metadata_fetch_success/failure` và `metadata_signature_invalid` theo registration.
- `metadata_valid_until_seconds_remaining` và thời gian từ lần validated refresh.
- `saml_registration_desired_revision` so với `applied_revision` trên từng node.
- `idp_signing_key_rollover_state`: PREPARED / OVERLAP / SWITCHED / RETIRED / EMERGENCY_REVOKED.
- `saml_response_signature_invalid_total`, `issuer_mismatch_total` và `authentication_success_rate` theo tenant.
- Tỉ lệ callback thất bại do pending AuthnRequest/session (để phân biệt signature errors với state errors).
- Certificate expiry/algorithm weakness/key usage policy issues và phân bổ signing method được quan sát trong **test/validated telemetry**.

Không đưa raw tenant names từ browser, account email hoặc unbounded algorithm URI vào metrics labels; dùng các registration IDs đã allowlist để tránh log injection/cardinality explosion.

## 19. Quy trình vận hành gợi ý cho một tenant

### 19.1. Before change

- Xác nhận tenant ID, owner, IdP entityID, metadata source và đúng IdP admin contact.
- Đọc bản active version, keys và thời gian hết hạn; phân loại signing/decryption/metadata signer/SP signing rotation.
- Có thay đổi issuer, endpoint, policy hay chỉ thêm key? Xác định blast radius và approval.
- Thử fetch/verify metadata trong staging; không thay active.
- Chuẩn bị test fixtures ký bằng old/new keys; không dùng assertions thật của khách hàng làm debug.
- Đặt lịch IdP switch **sau** SP readiness và có rollback/revocation plan.

### 19.2. During change

- Publish candidate validated version A với old+new certs trong đúng registration.
- Đợi mọi pods confirm applied version; kiểm tra SAMLResponse A-old và A-new.
- IdP chuyển signer sang A-new; theo dõi errors và latency.
- Tenant B/C phải tiếp tục hoạt động như trước; không restart toàn app nếu kiến trúc cho hot-swap an toàn.
- Giữ overlap có hạn, không tự kéo dài nếu có compromise.
- Audit change ID, version, outcome và IdP admin confirmation.

### 19.3. After change

- Chờ SAML in-flight window/IdP propagation và xác định không còn dùng A-old.
- Gỡ A-old khỏi A trusted verification keys, xác nhận B/C không đổi.
- Test A-old **reject** và A-new **accept**, cùng B-current **accept**.
- Xác nhận expiration/rotation reminder mới, metadata validUntil và monitoring.
- Chốt ticket và config history, tránh để một pod cũ tiếp tục trust A-old.
- Nếu phát hiện key compromise, thực hiện emergency incident response thay vì đóng change ticket bình thường.

## 20. Câu hỏi ôn tập

**1. Vì sao không thể dùng một danh sách public certificates của mọi IdP để verify mọi SAMLResponse?**  
Vì chữ ký đúng với certificate A không chứng minh IdP B hoặc tenant B đã phát message. Trust phải gắn với **registration/issuer được phê duyệt**.

**2. `registrationId`, `tenantId` và IdP entityID có luôn bằng nhau không?**  
Không. `registrationId` là khóa Spring Security; `tenantId` là ranh giới nghiệp vụ; IdP entityID do IdP định danh. Cần mapping xác minh.

**3. Khi IdP A gửi metadata có A-new, có nên tự thêm key ngay vào trusted set?**  
Chỉ khi metadata/source đã được xác minh theo bootstrap trust và candidate qua policy/approval. Không trust một key chỉ vì nó xuất hiện trong XML mới tải.

**4. Vì sao rollover cần giai đoạn A-old + A-new?**  
Để IdP có thể đổi signer mà SP vẫn verify in-flight responses, sau khi mọi SP nodes đã nhận key mới. Giai đoạn này phải có hạn.

**5. A-old bị compromise thì có giữ overlap để zero downtime?**  
Không. Phải revoke theo incident response, chấp nhận fail closed và phối hợp re-login/rotation.

**6. Metadata signed bằng cert mới có thể tự đưa cert đó vào `KeyDescriptor` để tự xác minh không?**  
Không. Metadata signature cần **trust anchor đã bootstrap ngoài metadata hiện tại**, không trust-on-first-use tùy ý.

**7. Nếu SP ký AuthnRequest cho A, thay IdP A verification key có làm đổi SP private signing key không?**  
Không. Hai chiều/credential roles khác nhau; cần rotation riêng.

**8. `validUntil` có cùng nghĩa `cacheDuration` và certificate `NotAfter` không?**  
Không. Metadata validity, caching guidance và X.509 certificate dates là các khái niệm riêng.

**9. `CachingRelyingPartyRegistrationRepository` tự làm metadata signature validation và refresh từng tenant an toàn chưa?**  
Không. Nó có contract caching/lazy loading; signature provenance, per-tenant validation, version approval và rollout vẫn phải được thiết kế/test. Class có từ Spring Security 6.4 theo API docs.

**10. Vì sao cập nhật metadata cần compare-and-swap/revision?**  
Để job bắt đầu từ bản cũ không ghi đè một bản mới đã duyệt, và các tenant khác không bị partial update.

**11. Có thể dùng email từ SAML Response để xác định tenant thay request state/issuer không?**  
Không. Email có thể trùng giữa tenants và chỉ là claim trong assertion; phải verify signature/registration và mapping tenant.

**12. Cách biết key rotation đã kết thúc an toàn?**  
Tất cả pods có revision đúng, A-new login pass, A-old đã bị reject sau retirement, B/C vẫn pass, SAML errors ổn định và change audit đã ghi.

## 21. Tài liệu chuẩn và API tham khảo

- [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): multiple `RelyingPartyRegistration`, builder, metadata loading, credential roles và request/response filters.
- [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): parsing/trusting IdP metadata, metadata signature verification với OpenSAML 5 và SP metadata endpoint.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): verification của IdP signatures, issuer, audience, conditions và customization.
- [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): outbound signing, IdP binding/metadata.
- [Spring Security API – CachingRelyingPartyRegistrationRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/CachingRelyingPartyRegistrationRepository.html): introduced in 6.4, caching loader/`setCache` và default no-expiry behavior.
- [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityDescriptor, IDPSSODescriptor, KeyDescriptor, endpoints, validUntil/cacheDuration.
- [OASIS SAML 2.0 Metadata Interoperability Profile](https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop.pdf): KeyDescriptor details, metadata trust/rollover, compromised vs retired key behaviors.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Response, Assertion, Issuer, Audience, InResponseTo, SubjectConfirmation.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): SAML signature trust, XML hardening, response validation và replay.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): chặn tải URL metadata không được phép, redirects/DNS controls.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): quản lý key lifecycle, rotation, compromise và secret storage.

**Kết luận:** Trong federation đa tenant, **metadata là cấu hình tin cậy**, không phải một file XML có thể tự động thay thế vô điều kiện. Mỗi tenant cần registration, issuer/endpoints, IdP verification keys, SP signing/decryption credentials và policy riêng hoặc sự chia sẻ được quản trị rõ. Luân chuyển key an toàn theo trình tự **pre-publish → validate → stage/approve → publish old+new → IdP/SP switch → observe → retire**, với emergency revoke khác routine overlap. Khi cập nhật phải có immutable revision, kiểm tra nguồn metadata, readiness của mọi pod và regression test tenant khác; tuyệt đối không mở global key trust hoặc tắt SAML validation để che lỗi rollout.