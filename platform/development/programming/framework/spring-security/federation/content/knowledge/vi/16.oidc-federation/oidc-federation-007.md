# Môi giới danh tính giữa ứng dụng và nhiều IdP bên ngoài

**Học phần:** Spring Security – federation → OIDC và môi giới.  
**Mục tiêu:** thiết kế và vận hành **Identity Broker** để các ứng dụng chỉ tích hợp với một nhà phát hành danh tính nội bộ, trong khi broker kết nối nhiều Identity Provider (IdP) bên ngoài bằng OpenID Connect (OIDC), SAML2 hoặc giao thức được hỗ trợ. Bài giải thích ranh giới tin cậy, luồng đăng nhập, ánh xạ danh tính, định tuyến IdP, bảo vệ token và cách triển khai ứng dụng Spring Security làm OIDC Relying Party (RP).

**Điểm cốt lõi:** broker **không chỉ là trang chọn nút đăng nhập**. Để môi giới OIDC thật sự, nó cần **xác minh thông điệp upstream**, liên kết subject bên ngoài với **tài khoản do broker quản lý**, thiết lập phiên của mình và **phát hành token OIDC mới dưới issuer của broker** cho ứng dụng downstream. Ứng dụng không được tin trực tiếp ID Token của IdP A như thể do broker ký hoặc dành cho audience của mình.

Bài hướng tới Java 17+, Spring Boot 4.1.x / Spring Security 7.x (Servlet/MVC) và một broker/OIDC Provider phù hợp. Các ví dụ miền `example.com` là dữ liệu học tập; cần thay bằng metadata, client registration và chứng thư/khóa đúng của hệ thống thực.

## 1. Vấn đề: một ứng dụng, nhiều nhà cung cấp danh tính

Một nền tảng B2B phục vụ ba nhóm:

- Nhân viên công ty dùng IdP nội bộ A, hỗ trợ OIDC.
- Đối tác doanh nghiệp B dùng IdP OIDC riêng.
- Đối tác lâu năm C chỉ cung cấp SAML2 IdP.
- Một ứng dụng web, mobile BFF, API và cổng quản trị cùng cần xác định tài khoản nội bộ, tenant, role và policy.

Nếu từng ứng dụng tích hợp trực tiếp với cả ba IdP, số kết nối, màn hình đăng nhập, cơ chế token, quy trình rotation và chính sách user mapping có xu hướng nhân lên. Mỗi ứng dụng phải hiểu IdP-specific claims, issuer, key rollover, lỗi callback và session/logout khác nhau. Rủi ro account collision tăng nếu các ứng dụng tùy tiện dùng email làm user ID.

**Identity Broker** tạo một điểm federation trung gian:

```text
             ┌──────────────────────────────┐
             │  App Web / BFF / Mobile / API │
             │  OIDC client hoặc resource    │
             │  server tin BROKER            │
             └──────────────┬───────────────┘
                            │ OIDC (broker issuer)
                            ▼
             ┌──────────────────────────────┐
             │      IDENTITY BROKER         │
             │ OIDC Provider với app        │
             │ OIDC RP / SAML SP với IdP    │
             │ Login routing               │
             │ Identity mapping / JIT      │
             │ Session, consent, policy    │
             │ Token issuance + JWKS       │
             └───────────┬─────┬────────────┘
                         │     │
                 OIDC ───┘     └── SAML2
                         │     │
             ┌───────────▼─┐ ┌─▼───────────┐
             │ IdP A / B   │ │ IdP C       │
             │ OIDC OP     │ │ SAML IdP    │
             └─────────────┘ └─────────────┘
```

**Phân biệt vai trò giao thức**:

| Chặng | Ai là client/RP? | Ai phát hành danh tính? | Token/callback |
| --- | --- | --- | --- |
| App → broker | Ứng dụng là **OIDC RP/OAuth client** | Broker là **OIDC Provider/Authorization Server** | App nhận authorization code rồi đổi lấy broker ID Token |
| Broker → IdP A | Broker là **OIDC RP** của IdP A | IdP A là **OIDC Provider** | Broker nhận và xác minh **upstream ID Token** |
| Broker → IdP C | Broker là **SAML2 SP** | IdP C là **SAML2 Identity Provider** | Broker xác minh `SAMLResponse/Assertion` |
| API → broker | API là **OAuth2 resource server** | Broker phát access token dành cho API | API kiểm tra `iss`/`aud`/chữ ký/scope theo policy |

**OIDC dùng để xác thực**, xây trên OAuth2; một IdP chỉ cung cấp OAuth2 authorization không tự tương đương OIDC. Nếu provider không phát ID Token, broker phải có cơ chế nhận diện user rõ ràng từ provider API được tin cậy và không gán nhãn ID Token giả.

## 2. Ba kiến trúc thường bị nhầm

| Kiến trúc | Thực tế | Khi phù hợp | Điểm cần chú ý |
| --- | --- | --- | --- |
| **Ứng dụng tích hợp nhiều OIDC IdP trực tiếp** | Spring `oauth2Login` có nhiều `ClientRegistration`, ứng dụng nhận token từ từng IdP | Một ứng dụng nhỏ, ít upstream providers | **Đây chưa phải broker** nếu ứng dụng không phát token cho client downstream |
| **Identity Broker/OIDC Provider** | Ứng dụng chỉ biết broker; broker giao tiếp nhiều upstream, xây internal subject và phát token mới | Nhiều app/tenant/IdP, cần chính sách và federation thống nhất | Broker trở thành trust-critical service cần HA, key management, auditing |
| **Gateway đẩy header danh tính** | Gateway làm login rồi gửi `X-User`/`X-Email` nội bộ | Một số ứng dụng legacy không có OAuth2/OIDC | Chỉ an toàn với network/mTLS/header stripping; **không tự là OIDC broker** |

**Không nhầm Spring Security `oauth2Login()` với OIDC Provider.** `oauth2Login()` cung cấp chức năng **OAuth2/OIDC client login**, tức RP với IdP; muốn một ứng dụng Spring vừa nhận login upstream vừa phát authorization codes/ID Tokens downstream, cần thêm **Authorization Server/OP implementation** (Spring Security OAuth2 Authorization Server hoặc sản phẩm IAM) cùng đăng ký client, keys, discovery, session, consent, logout và chính sách mapping. Không chỉ gọi một annotation là có thể “biến client thành broker”.

### 2.1. Dùng sản phẩm IAM hay tự xây broker?

| Phương án | Ưu điểm | Trách nhiệm cần dự trù |
| --- | --- | --- |
| Keycloak / IAM có identity brokering | Có nhiều adapter OIDC/SAML, login flows, federated identity links, user management | Cấu hình client, upstream trust, first-broker-login, chống auto-link email, rotation và HA |
| Managed identity service có federation | Giảm vận hành server/khóa; hỗ trợ giao diện, policy và audit tùy dịch vụ | Vendor contracts, dữ liệu vùng lưu trú, limits, ràng buộc logout và migration |
| Spring Security + Authorization Server tự xây | Linh hoạt claims, business policy, tích hợp sâu Java | Tự sở hữu toàn bộ ranh giới an ninh: credential lifecycle, discovery, token validation/issuance, linking, SLO và kiểm thử |

Với nhiều IdP thực tế, **ưu tiên sản phẩm IAM đã được kiểm chứng** nếu yêu cầu phù hợp. Chỉ xây broker riêng khi có đội chịu trách nhiệm an ninh, protocol interoperability, HSM/secrets, audit và incident response.

## 3. Luồng OIDC brokered login từ đầu đến cuối

Giả sử:
- App: `https://portal.example.com`, OIDC client ID `portal-web`.
- Broker: `https://login.example.com/realms/partners`, issuer ổn định.
- Upstream A: `https://idp-a.partner.example/oidc`.
- Upstream B: `https://idp-b.partner.example/oidc`.
- Ứng dụng chỉ cấu hình **broker issuer**, không cấu hình từng upstream issuer.

```mermaid
sequenceDiagram
    actor User as Người dùng
    participant App as Portal (OIDC RP)
    participant Broker as Identity Broker (OIDC OP)
    participant Link as Identity Link DB
    participant IdP as External OIDC IdP A
    User->>App: GET /private
    App-->>User: Redirect tới broker /authorize với state, nonce, PKCE
    User->>Broker: OIDC authorization request
    Broker->>Broker: Chọn IdP A theo policy đã tin
    Broker-->>User: Redirect tới IdP A /authorize (upstream state/nonce/PKCE riêng)
    User->>IdP: Xác thực user
    IdP-->>User: Redirect upstream code về broker callback
    User->>Broker: code + state cho upstream transaction
    Broker->>IdP: Đổi code với verifier và client credentials phù hợp
    IdP-->>Broker: Upstream ID Token + token response
    Broker->>Broker: Verify iss, aud, signature, nonce, exp, policy
    Broker->>Link: Lookup (upstream issuer, upstream sub, scope)
    Link-->>Broker: broker subject B-100 hoặc yêu cầu linking/JIT
    Broker->>Broker: Tạo session và authorize downstream client
    Broker-->>User: Redirect authorization code đến App
    User->>App: code + state của downstream transaction
    App->>Broker: Đổi code với verifier/client authentication
    Broker-->>App: Broker ID Token, access token nếu được cấp
    App->>App: Verify broker iss, aud, signature, nonce, expiry
    App-->>User: Session tại portal, authorization theo tenant
```

**Hai authorization codes và hai bộ state/nonce/PKCE độc lập:** code do upstream A cấp chỉ được broker đổi tại token endpoint của A; code do broker cấp chỉ được app đổi tại token endpoint của broker. Không dùng upstream code để callback thẳng vào app hoặc hoán đổi token giữa hai authorization servers.

### 3.1. Quan hệ tin cậy

1. App → broker: app tin **public signing keys/JWKS, issuer và metadata của broker**, đã đăng ký `client_id`/`redirect_uri` tại broker.
2. Broker → upstream A: broker tin issuer/discovery/JWKS của A và có **client registration riêng tại A**.
3. Broker → upstream B: một client registration và trust anchor riêng.
4. Broker → SAML C: broker có SP metadata và chứng thư, tin SAML Issuer/signing cert của C và kiểm chứng SAML assertions.
5. Application authorization: quyền tenant/role/resource được kiểm tra **sau khi** brokered authentication; không mặc nhiên coi một external group là quyền admin nội bộ.

**Không dùng certificate/JWKS của upstream A để kiểm tra broker ID Token**, cũng không dùng JWKS broker để xác minh upstream token. Mỗi issuer có khóa, audience và trust boundary riêng.

## 4. ID Token do broker phát và ranh giới token

Một upstream ID Token minh họa sau khi đã xác minh:

```json
{
  "iss": "https://idp-a.partner.example/oidc",
  "sub": "user-938",
  "aud": "broker-client-at-idp-a",
  "iat": 1794020400,
  "exp": 1794024000,
  "auth_time": 1794020350,
  "acr": "urn:example:idp-a:loa2"
}
```

Một downstream ID Token **khác** do broker ký để gửi riêng cho app:

```json
{
  "iss": "https://login.example.com/realms/partners",
  "sub": "B-100",
  "aud": "portal-web",
  "iat": 1794020420,
  "exp": 1794020720,
  "auth_time": 1794020350,
  "tenant_id": "partner-a"
}
```

Đây là **payload minh họa, không phải JWT hoàn chỉnh hay bằng chứng chữ ký**. Các mốc `iat/exp/auth_time` chỉ là con số ví dụ; broker phải sinh giá trị có nghĩa, tuân thủ thời gian hiện tại và profile của từng bên. `tenant_id` là **custom claim** phải được bảo vệ, định nghĩa và kiểm tra theo policy; không tự là claim OIDC chuẩn.

**Điểm quan trọng:**
- `iss` downstream **luôn là issuer broker**, không phải issuer upstream A.
- `sub` downstream là subject do broker quản lý, có thể là **opaque/pairwise**, không tự bằng email hoặc upstream `sub`.
- `aud` downstream **phải là client ID của app**; ID Token upstream có audience dành cho broker **không thể sử dụng để đăng nhập app**.
- Broker phải phát token mới bằng signing key của chính broker và hỗ trợ JWKS/rotation; **không** copy upstream JWT rồi đổi `iss`/`aud` bằng cách sửa payload.
- Upstream `acr/amr/auth_time` không nên được copy nguyên như chứng minh assurance cấp cao hơn nếu broker chưa kiểm tra ý nghĩa, freshness và hợp đồng của IdP. Nếu muốn truyền, broker cần policy transformation có thể audit.
- App chỉ xử lý **downstream ID Token**, broker có thể lưu provenance upstream có kiểm soát tại server phục vụ audit/account linking.

### 4.1. ID Token khác Access Token

| Token | Dành cho | Có được thay thế bằng token khác không? |
| --- | --- | --- |
| **ID Token** | OIDC RP chứng thực người dùng với `aud=client_id` | Không gửi làm bearer token cho API như một quy tắc mặc định |
| **Access Token** | OAuth2 resource server, có scopes và audience phù hợp | Không xem nó mặc nhiên là bằng chứng identity login của một RP |
| **Refresh Token** | Client xin access token mới theo policy | Bảo vệ bí mật, rotation/revocation; không gửi cho browser không phù hợp |
| **Upstream token** | Broker/ứng dụng client trực tiếp đối với upstream issuer | Không chuyển thẳng đến downstream APIs nếu thiếu explicit token exchange và trust contract |
| **Broker token** | Downstream RP/API theo audience được cấp | Không thể dùng mặc định tại upstream API vì khác issuer/audience |

Nếu broker cần gọi API bên thứ ba thay mặt user, phải thiết kế riêng authorized-client/token storage, scopes, consent, refresh và token exchange/delegation theo provider. **Không forwarding một upstream access token tới mọi microservice** chỉ vì login thành công. Token exchange, nếu dùng, cần authorization server hỗ trợ, kiểm soát audience và audit.

## 5. ID Token validation ở **hai chặng** là bắt buộc

### 5.1. Broker xác minh token từ IdP bên ngoài

Khi broker nhận upstream response:
- `iss` đúng issuer URI đã được cấu hình/discovered cho **chính upstream transaction**; không tự chọn nhà phát hành từ giá trị chưa kiểm chứng.
- `aud` chứa **broker client ID tại IdP ấy**, và xử lý `azp` theo OIDC profile khi có.
- Chữ ký dùng public keys/JWKS của **đúng issuer**, thuật toán nằm trong allowlist.
- `exp` chưa hết hạn, `iat` hợp lệ, `nonce` khớp request đã gửi khi áp dụng, `state`/PKCE đúng giao dịch.
- `sub` có mặt và có ý nghĩa ổn định trong namespace issuer; `email` chỉ là thông tin profile có vòng đời riêng.
- Nếu UserInfo endpoint được gọi, `sub` trả về phải khớp `sub` trong ID Token như OIDC Core yêu cầu.
- Nếu upstream dùng SAML, xác minh chữ ký Response/Assertion, `InResponseTo`, audience, recipient, issuer, thời hạn và NameID theo profile thay vì cố dùng OIDC JWT validator.

Broker **không** cho phép yêu cầu browser chỉ định URL `issuer-uri`/`jwk-set-uri`/`token-uri` tùy ý rồi tự tin tưởng chúng. Đó có thể dẫn đến SSRF, lấy metadata độc hại hoặc token endpoint attacker kiểm soát.

### 5.2. App xác minh token từ broker

App OIDC RP:
- `iss` bằng **broker issuer** đã đăng ký, đối chiếu chính xác chuỗi URI theo OIDC.
- `aud` chứa app `client_id`; khi multiple audiences, kiểm tra `azp` và trusted audiences theo OIDC.
- Chữ ký/JWS bằng broker JWKS được lấy từ discovery đáng tin, không chấp nhận `alg=none` hoặc thuật toán trái policy.
- `exp/iat` hợp lệ, `nonce` khớp request OIDC khi áp dụng; `state` được ràng buộc với browser/request.
- Authorization Code + **PKCE** theo OAuth2 Security BCP, redirect URI đăng ký **exact-match**.
- `sub` là identity key phía broker; account/tenant authorization phía ứng dụng vẫn phải được thực hiện.

Một resource server không chỉ kiểm `iss` và chữ ký rồi bỏ `aud`. JWT có thể hợp lệ nhưng dành cho một client/API khác. Khi API cần một `aud` cụ thể, phải cấu hình audience validator/resource policy phù hợp.

### 5.3. Vì sao cùng token của IdP A không thể dùng cho app B?

Upstream token có `aud=broker-client-at-idp-a`. Nếu app B chấp nhận token đó khi `aud≠app-b`, nó có thể bị **token substitution/confused deputy**: một token cấp cho mục tiêu khác được dùng như credential của app B. Broker phải phát hành token downstream có đúng audience/app policy; app verify riêng. Việc issuer/signer hợp lệ ở một chặng **không tạo trust tự động ở chặng khác**.

## 6. Lựa chọn IdP (Home Realm Discovery) an toàn

Khi người dùng mở màn hình login, broker có thể cung cấp:
1. **Trang chọn IdP** theo tổ chức, branding và policy.
2. **Domain discovery**: người dùng nhập email tổ chức, broker gợi ý IdP, nhưng email domain **chỉ dùng để định tuyến/UX**, không tự chứng minh tenant/identity.
3. **Invitation hoặc tenant slug** từ máy chủ: chọn IdP đã được liên kết với tenant qua bảng cấu hình.
4. **Federation hints**: một số vendor hỗ trợ parameter như `kc_idp_hint` của Keycloak hoặc `login_hint`; chúng không phải xác minh danh tính.
5. **SAML IdP discovery/metadata** theo hợp đồng bên ngoài.

**Ranh giới:** routing quyết định “gửi browser sang đâu”, còn **issuer validation và account mapping** mới quyết định “ai đã xác thực và có quyền gì”. Browser có thể sửa query parameter, email hoặc tenant hint, nên tuyệt đối không dùng chúng làm authority.

### 6.1. Bảng IdP allowlist theo tenant

| Tenant | Allowed upstream issuer | Protocol | Chính sách |
| --- | --- | --- | --- |
| `company` | `https://sso.company.example` | OIDC | Nhân viên, MFA theo org |
| `partner-a` | `https://idp-a.partner.example/oidc` | OIDC | Invitation + identity linking |
| `partner-b` | `https://idp-b.partner.example/oidc` | OIDC | Chỉ user đã provision |
| `legacy-c` | SAML entityID từ metadata đã ký | SAML2 | Stable NameID, stricter mapping |

Nếu attacker thêm `?tenant=company` vào URL của partner B, broker không thể vì vậy chuyển identity của B thành nhân viên `company`. Chỉ map issuer/subject sang tenant khi có identity-link/membership được cấp phép.

### 6.2. Redirect và mix-up khi có nhiều upstream

Một broker là OAuth client giao tiếp với **nhiều authorization servers**, nên dễ chịu **authorization server mix-up** nếu callback hoặc stored authorization request không xác định đúng issuer. Theo RFC 9700:
- Dùng `state` ngẫu nhiên một lần, gắn session/browser với **đúng upstream issuer + client registration**.
- Ưu tiên authorization response issuer identification `iss` theo RFC 9207 khi provider hỗ trợ; kiểm tra issuer với issuer đã lưu.
- Có thể dùng **redirect URI khác nhau theo issuer** làm biện pháp thay thế được RFC 9700 mô tả khi phù hợp.
- Đổi authorization code **chỉ tại token endpoint thuộc issuer được chọn ban đầu**, không lựa endpoint từ query param của callback.
- Dùng PKCE, HTTPS, exact redirect matching, bảo vệ secret và không tạo open redirect.
- Validation thêm ID Token issuer/audience/nonce ở token endpoint không thay thế toàn bộ bảo vệ mix-up ở authorization response.

Chỉ lưu URL `authorization_endpoint` không đủ bảo vệ mix-up nếu attacker có thể cấu hình một token endpoint khác cùng metadata. Upstream client registration phải do admin quản lý và được kiểm duyệt.

## 7. Ánh xạ danh tính qua nhiều IdP: không dùng email làm khóa

Trong OIDC, hai claim nền tảng dùng nhận diện subject là:
- `iss`: issuer của Provider đã được xác minh.
- `sub`: định danh subject ổn định **trong namespace issuer** theo OIDC Core.

**External identity key khuyến nghị** là tuple `(trusted upstream issuer, upstream sub)`, thêm scope/tenant nếu hợp đồng subject tương ứng không toàn cục trong issuer. Với upstream SAML, dùng `(trusted SAML issuer, stable NameID, qualifiers/SP scope khi cần)`.

| Upstream Issuer | Upstream sub | Email | Kết luận |
| --- | --- | --- | --- |
| IdP A | `abc-7` | `alice@a.example` | External subject A |
| IdP B | `abc-7` | `alice@a.example` | **Khác subject A** vì issuer khác |
| IdP A | `abc-9` | `alice@a.example` | Không tự link vào A chỉ vì email giống |
| IdP A | `abc-7` | `alice@new.example` | Cùng external subject nếu issuer/sub giữ nguyên |

Email có thể đổi hoặc tái cấp cho người khác. `email_verified=true` chỉ cho biết nhà phát hành có một cơ sở xác minh email theo chính sách của họ; **không chứng minh danh tính giữa hai issuer là cùng một con người**, nhất là khi onboarding hoặc account linking có rủi ro account takeover.

### 7.1. Ba lớp ID

```text
upstream:  (issuer_A, sub_abc7)
                        │
                        ▼
broker:   broker_user_id = U-100
                        │
                        ▼
downstream client: broker sub = opaque_B100
                        │
                        ▼
app:      internal_user_id / memberships / permissions
```

Broker có thể:
- Dùng cùng broker `sub` với nhiều clients (`public sub`).
- Dùng `pairwise sub` khác nhau cho từng RP/sector (phụ thuộc broker policy); vẫn map về broker user nội bộ.
- Có nhiều external links từ các IdP cho **một broker user** khi liên kết đã được chứng minh.

App downstream **không nhất thiết thấy** upstream issuer/sub. Nếu cần audit nguồn authentication, broker có thể phát một custom claim đã ký và kiểm soát hoặc lưu ở server; không biến custom claim này thành identity key duy nhất mà bỏ `iss=broker` và `sub`.

### 7.2. Database mapping gợi ý

```sql
CREATE TABLE broker_users (
    user_id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE external_identities (
    identity_id UUID PRIMARY KEY,
    broker_user_id UUID NOT NULL REFERENCES broker_users(user_id),
    upstream_issuer TEXT NOT NULL,
    upstream_subject TEXT NOT NULL,
    provider_scope TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (upstream_issuer, upstream_subject, provider_scope)
);

CREATE INDEX idx_external_by_user
    ON external_identities(broker_user_id);

CREATE TABLE tenant_memberships (
    tenant_id TEXT NOT NULL,
    broker_user_id UUID NOT NULL REFERENCES broker_users(user_id),
    role_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, broker_user_id, role_name)
);
```

Đây là lược đồ đơn giản để dạy **cấu trúc**, không bao phủ toàn bộ concurrency/migration/audit. `provider_scope` phải có canonical value rõ; với OIDC đơn giản thường cố định theo issuer (không được tự chèn tenant bất kỳ để cho phép hai user trùng), còn với SAML có thể là NameID qualifier/SP scope theo hợp đồng. Nếu có nhiều membership/role, chuẩn hóa trong hệ thống role riêng.

Trong JIT provisioning:
1. Broker **xác minh upstream response** trước.
2. Kiểm tra IdP được phép tại tenant/onboarding policy.
3. Tìm link theo canonical external key với unique index.
4. Nếu chưa có: chỉ tạo broker user/link khi policy cho phép, trong transaction có bảo vệ race.
5. Nếu email trùng với user đã tồn tại: **không tự link**, yêu cầu proof về tài khoản cũ, invitation/SCIM/admin approval.
6. Trước khi phát token cho app, kiểm tra trạng thái `ACTIVE`/tenant membership, không mặc định cấp role cao.
7. Đăng sự kiện audit không chứa raw token/secret.

**Không tạo login “fail-open”:** nếu user chưa được provision mà JIT không cho phép, trả lỗi onboarding có kiểm soát, không tự cấp tenant membership mặc định.

## 8. Account linking, migration và deprovision

### 8.1. Link cùng người ở IdP A và B

Một user đã có broker account U-100 qua IdP A, muốn đăng nhập thêm bằng IdP B. Đúng quy trình:
- User đang có phiên broker được xác thực và vượt qua reauthentication/CSRF defense phù hợp.
- Broker **chủ động** bắt đầu upstream login B theo account-linking workflow, không dựa vào input email hoặc `sub` gửi từ client.
- B xác thực, broker kiểm chứng token issuer/subject của B và security state.
- User (hoặc admin theo chính sách) xác nhận liên kết B → U-100.
- Broker ghi link mới trong transaction với uniqueness, không cho B đã liên kết với U-999 bị chiếm.
- Audit ai/when/from-where; có flow unlink/revoke với guard không khóa người dùng ra khỏi tài khoản.

Keycloak có **First Broker Login flow**, identity provider settings và account linking workflows. Tùy chọn `Trust Email` phải được đánh giá thận trọng: nếu tin email sai trong first-login linking có thể dẫn đến account takeover. Không bật automatic email-based linking chỉ để giảm bước onboarding.

### 8.2. User đổi email/department

Nếu upstream `iss+sub` giữ nguyên, broker user ID không đổi. Email là profile attribute/địa chỉ liên hệ, có thể cập nhật theo policy nhưng không thay khóa. Role/tenant membership phải theo nguồn có authority và quy trình cấp phát phù hợp.

### 8.3. Đổi IdP hoặc hợp nhất tổ chức

Đổi từ IdP A sang B **không có phép ánh xạ tự động** giữa hai `sub`. Muốn giữ lịch sử/broker user:
- Mapping có bằng chứng từ SCIM/HR/directory và IdP owners; hoặc
- Người dùng chứng minh quyền sở hữu cả A và B trong phiên đã xác thực; hoặc
- Admin migration có phê duyệt, audit và rollback.

Nếu issuer URI hoặc pairwise `sub` thay khi tạo application registration mới, coi là **thay đổi identity namespace** và thử trước khi rollout. Không sửa SQL hàng loạt chỉ bằng email domain.

### 8.4. Disable user và vòng đời phiên

Một user bị khóa tại upstream chưa chắc bị logout tức thì tại broker hoặc các app: broker có session/token riêng. Cần SCIM/event/webhook đáng tin, short TTL và refresh policy, revocation, kiểm tra trạng thái broker user. App có thể phải kiểm tra authorization hiện tại thay vì chỉ tin token dài hạn.

**Logout đa chặng không mặc định đồng bộ.** App logout local, broker RP-initiated logout, broker logout upstream, OIDC front-/back-channel logout hoặc SAML SLO là những hành vi khác nhau. Tài liệu OIDC Back-Channel Logout mô tả thông điệp với `iss/sub/sid`; việc chuyển tín hiệu từ upstream sang broker rồi downstream cần cấu hình và test vendor-specific. Nếu IdP upstream còn SSO session, lần login sau có thể đi qua silently.

## 9. Spring Security: ứng dụng downstream chỉ kết nối broker

Đây là phần **runnable framework example** đơn giản: một ứng dụng Spring Boot 4.1.x dùng `oauth2Login`, kết nối **một issuer broker** bằng OIDC Authorization Code Flow. Nếu broker đã cấu hình IdP A/B/C, app này **không cần biết** A/B/C ở OAuth2 client registrations.

### 9.1. `pom.xml` đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>portal-oidc-client</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

**Chú ý phiên bản:** Trong Boot 4, `spring-boot-starter-security-oauth2-client` là starter theo cấu trúc mới; tên cũ `spring-boot-starter-oauth2-client` có thể còn tồn tại nhưng deprecated theo metadata. Boot 3.x có dependency khác; không trộn major nếu chưa kiểm thử.

### 9.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: portal-web
            client-secret: ${BROKER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          broker:
            issuer-uri: https://login.example.com/realms/partners

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
```

Trước khi chạy phải có **OIDC Provider thật** tại issuer URL và một OAuth client `portal-web` đã được đăng ký với broker, redirect URI khớp chính xác. `BROKER_CLIENT_SECRET` phải được lấy từ secret manager/environment, không commit vào Git. Với local development không có HTTPS, cần cấu hình cookie dành riêng cho dev; không tắt `Secure` trong production.

Spring Security sử dụng discovery tại broker issuer để tìm authorization endpoint, token endpoint và JWKS. **Không đặt issuer-uri là upstream A/B** nếu kiến trúc mong muốn là broker. Khi broker issuer đổi, đó là thay đổi trust contract cho tất cả downstream apps.

### 9.3. `SecurityConfig.java`

```java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated()
                )
                .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

### 9.4. `PortalApplication.java`

```java
package com.example.portal;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PortalApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortalApplication.class, args);
    }

    @GetMapping("/")
    String home() {
        return "Portal using OIDC broker";
    }

    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        var idToken = user.getIdToken();
        return Map.of(
                "issuer", idToken.getIssuer().toExternalForm(),
                "subject", idToken.getSubject()
        );
    }
}
```

Sau khi cấu hình broker thật, chạy:

```bash
mvn test
mvn spring-boot:run
```

Mở `/me` sẽ chuyển browser tới broker login (khi chưa xác thực), broker tiếp tục đến upstream IdP được chọn. Khi thành công, JSON hiển thị **issuer broker** và **sub broker**, chứ không nhất thiết có issuer/sub IdP A. Không có stdout/HTTP JSON cố định vì subject, client và session đến từ broker thực tế. Đoạn code cố ý không trả ID Token raw, access token hoặc email ra client.

**Mẫu chỉ thể hiện đăng nhập downstream, không chứa toàn bộ implementation broker.** Broker phải đã có issuer, keys, registered clients và federation links từ trước.

### 9.5. Điều gì xảy ra khi có nhiều upstream IdP?

Không sửa `application.yml` của portal để thêm `partner-a` và `partner-b` như OIDC providers trực tiếp. Thay vào đó cấu hình **trong broker** hai external IdPs và routing/linking policies. Ứng dụng chỉ thấy:
- `iss=https://login.example.com/realms/partners`.
- `sub` do broker quản lý.
- Claims do broker được ủy quyền phát cho app.
- Broker signing key/JWKS và session/authorization APIs của broker.

Nếu app cần quyền theo tenant, triển khai mapping/authorization trên broker user ID và internal business database; không chỉ đọc `preferred_username`/`email`.

## 10. Spring Security ở **phía upstream broker**: nhiều registrations

Nếu tổ chức tự xây broker bằng Spring, tầng login upstream có thể dùng `oauth2Login` với nhiều `ClientRegistration` như bên dưới. Nhưng **tầng này chỉ là OIDC RP**; chưa tự phát OIDC ID Token cho portal. Tầng downstream OP phải được triển khai bằng **Spring Security OAuth2 Authorization Server** hoặc một IAM/OIDC provider khác.

### 10.1. Cấu hình hai upstream OIDC providers (mảnh YAML)

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          idp-a:
            provider: idp-a
            client-id: broker-at-idp-a
            client-secret: ${IDP_A_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          idp-b:
            provider: idp-b
            client-id: broker-at-idp-b
            client-secret: ${IDP_B_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          idp-a:
            issuer-uri: https://idp-a.partner.example/oidc
          idp-b:
            issuer-uri: https://idp-b.partner.example/oidc
```

Hai start endpoints mặc định thường là:
- `GET /oauth2/authorization/idp-a`.
- `GET /oauth2/authorization/idp-b`.

Callback endpoints:
- `GET /login/oauth2/code/idp-a`.
- `GET /login/oauth2/code/idp-b`.

Mỗi upstream cần client registration, exact redirect URI, keys, secret/PKCE và trust riêng. **Không đánh đồng `registrationId=idp-a` với upstream issuer URI**; issuer xác định từ trusted configuration và token validation.

### 10.2. Broker phải có tầng Authorization Server/OP riêng

Để cấp ID Token cho portal, broker cần:
- Một **stable issuer URI** và OIDC discovery `/.well-known/openid-configuration`.
- Authorization endpoint/token endpoint/JWKS endpoint, khóa ký và key rotation.
- Registered clients, redirect URI allowlist, client authentication, grants/scopes/consent.
- Authorization Code Flow + PKCE và session quản lý browser/user.
- Mapping upstream identities sang **broker user ID** bất biến.
- Token customization: `iss` broker, `sub` broker subject, `aud` đúng downstream client, claims theo policy; không chuyển nguyên upstream token.
- Logout, revocation, refresh token policy, monitoring và incident response.
- Bảo vệ issuer mix-up khi chính broker giao tiếp nhiều upstream.

Spring Security 7 có feature **OAuth2 Authorization Server**; Spring Authorization Server chuyển vào Spring Security 7 theo thông báo chính thức. Một ví dụ có thể tham khảo [How-to: Authenticate using Social Login](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-social-login.html). Tuy nhiên guide “social login” **không tự xử lý mọi yêu cầu broker đa tenant**: account linking an toàn, protocol translation SAML, logout cascading, provenance, step-up, high availability và key management cần được thiết kế bổ sung.

### 10.3. Broker hỗ trợ SAML upstream như thế nào?

Tại chặng broker → SAML IdP, broker đóng vai **SAML Service Provider**, có thể dùng Spring Security `saml2Login` và `RelyingPartyRegistration` hoặc adapter trong IAM. Broker cần xác minh:
- IdP `Issuer` và trusted certificate.
- XML signature, audience, recipient/ACS, `InResponseTo` và request/session correlation.
- `NameID` ổn định theo IdP contract; qualifier/SP scope khi cần.
- Validity window, replay, tenant binding, encrypted assertion nếu IdP yêu cầu.

Sau đó broker map external SAML identity sang broker user và phát **OIDC token mới** cho app. **SAMLResponse không phải OIDC ID Token**; không thể chỉ Base64 decode XML rồi tạo `sub=email` mà bỏ account linking. Protocol translation là một authentication boundary cần audit và kiểm thử.

## 11. Java 17 độc lập: tại sao cần issuer + subject

Bài tập sau chạy được bằng JDK 17+ **không cần Spring hoặc mạng**. Nó mô phỏng broker identity linking: hai upstream có thể phát cùng `sub` nhưng không phải cùng người; broker có internal user ID riêng. Ví dụ **không xử lý chữ ký/nonce/token**, vì vậy chỉ dùng cho kiến thức mapping.

Tệp `IdentityBrokerDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class IdentityBrokerDemo {
    record ExternalSubject(String issuer, String subject) {
        ExternalSubject {
            if (issuer == null || subject == null
                    || issuer.isBlank() || subject.isBlank()) {
                throw new IllegalArgumentException(
                        "Issuer and subject are required");
            }
        }
    }

    public static void main(String[] args) {
        String brokerIssuer = "https://login.example.com/realms/partners";

        ExternalSubject idpA = new ExternalSubject("idp-A", "user-42");
        ExternalSubject idpARepeat =
                new ExternalSubject("idp-A", "user-42");
        ExternalSubject idpB = new ExternalSubject("idp-B", "user-42");

        Map<ExternalSubject, String> links = new HashMap<>();
        links.put(idpA, "broker-user-100");

        System.out.println("Same subject + same issuer: "
                + idpA.equals(idpARepeat));
        System.out.println("Same subject + different issuer: "
                + idpA.equals(idpB));
        System.out.println("Known broker user: "
                + links.get(idpARepeat));
        System.out.println("Other provider: "
                + links.getOrDefault(idpB, "unlinked"));
        System.out.println("Downstream issuer: " + brokerIssuer);
    }
}
```

Biên dịch/chạy:

```bash
javac IdentityBrokerDemo.java
java IdentityBrokerDemo
```

**Stdout chính xác:**

```text
Same subject + same issuer: true
Same subject + different issuer: false
Known broker user: broker-user-100
Other provider: unlinked
Downstream issuer: https://login.example.com/realms/partners
```

**Ý nghĩa:** `record` so sánh hai thành phần đầy đủ, tránh va chạm do dùng mỗi `sub`. External subject được liên kết vào broker user theo database/policy riêng. Một application-facing broker `sub` có thể là chuỗi opaque khác, không phải cùng upstream subject. **Không copy map trong demo thành security provider production**: đầu vào ở đây giả định đã xác minh, còn hệ thống thật bắt buộc xác minh JWT/SAML, quản lý keys, account linking, transaction/race và policy.

## 12. Multi-tenant và cách truyền quyền

Một broker có thể phục vụ các tổ chức B2B nhưng **authentication authority không đồng nghĩa business authorization authority**.

**Mô hình nên tách:**
1. `External identity`: IdP issuer + sub/NameID đã xác minh.
2. `Broker user`: internal broker account id, enabled/disabled.
3. `Tenant membership`: quan hệ user–tenant có lifecycle/invitation/provisioning.
4. `Application roles`: quyền cụ thể cho app/api; có thể do app DB quản lý.
5. `Assurance state`: `auth_time`, `acr`, `amr` và session policy để xử lý step-up.

Các group/role upstream không có ý nghĩa toàn cục: `admin` từ IdP A có thể chỉ là quản trị hệ thống của đối tác A, **không thể** tự trở thành `ROLE_ADMIN` của portal nội bộ.

Nếu broker muốn phát claim `roles`/`tenant_ids` downstream:
- Ràng buộc IdP issuer, claim namespace và allowlist mapping.
- Chỉ phát quyền do broker/application IAM có authority quản lý.
- Tránh nhồi danh sách quyền khổng lồ vào JWT, đặc biệt khi quyền thay đổi thường xuyên.
- API phải kiểm tra đúng `aud`, scopes/roles và tenant của **resource**, không chỉ kiểm chữ ký.
- Cân nhắc token TTL ngắn, permission lookup hoặc introspection cho quyền nhạy cảm có thể bị thu hồi.

**JIT provisioning** có thể tạo broker account nhưng không tự cấp membership. SCIM có thể quản lý vòng đời user/membership; nhất quán giữa SCIM/IdP events, broker sessions và app authorization là trách nhiệm vận hành cần thiết.

## 13. MFA, step-up và thời gian xác thực qua broker

OIDC có các claim:
- `auth_time`: thời điểm xác thực cuối được OP tuyên bố.
- `acr`: authentication context class reference theo policy/provider.
- `amr`: các phương thức xác thực được OP khai báo.
- `max_age` trong auth request: yêu cầu thời hạn gần nhất của authentication, cần xử lý theo OIDC.
- `prompt=login`: yêu cầu tương tác đăng nhập lại theo semantics OIDC.

Trong mô hình broker:
1. App gửi yêu cầu step-up tới broker theo giao thức/policy đã thỏa thuận.
2. Broker xác định user/IdP upstream và có thể truyền `max_age`, `prompt`, `acr_values` hoặc SAML `ForceAuthn/RequestedAuthnContext` theo khả năng provider.
3. Broker kiểm chứng **upstream auth_time/acr/amr** hoặc `AuthnStatement/AuthnContext` từ IdP.
4. Broker chỉ phát downstream `auth_time/acr/amr` **theo nghĩa đã được kiểm chứng và cam kết**, không copy text upstream tùy tiện.
5. App kiểm tra đúng assurance/freshness và user continuity, không coi login broker thành công là bằng chứng MFA phù hợp mọi hành động.

Có IdP không hỗ trợ step-up/mapping context tương đương. Khi chính sách bắt buộc, broker phải báo không thể đáp ứng hoặc từ chối hành động, **không hạ mức bằng cách đổi claim string thành MFA**.

## 14. Logout và phiên trên ba chặng

Một login brokered có ít nhất:
- Phiên ứng dụng downstream (ví dụ `JSESSIONID` của portal).
- Phiên của broker, dùng để SSO giữa nhiều app.
- Phiên của IdP A/B/C.
- Authorization codes/access/refresh tokens ở những chặng có thiết kế cấp token.

Bảng hành vi:

| Sự kiện | Điều có thể xảy ra | Điều không được tự giả định |
| --- | --- | --- |
| Người dùng logout portal | App xóa SecurityContext/local session | Broker và upstream IdP cũng logout |
| Người dùng logout broker | Broker xóa session, có thể thông báo downstream | Mọi downstream nhận back-channel logout thành công |
| Upstream IdP logout | Broker có thể được thông báo qua protocol hỗ trợ | Mọi browser/app session tự mất ngay |
| Thu hồi user ở IdP | IdP chặn login mới | Token broker đã cấp lập tức hết giá trị |
| Broker key rotation | JWKS công bố key mới, clients refresh | Các app tự chấp nhận key mới nếu pin cấu hình sai |
| Token expire | Token không còn được resource server chấp nhận | Browser IdP/broker session chắc chắn đã kết thúc |

**OIDC RP-Initiated Logout** và **Back-Channel Logout** là các specification riêng. Broker phải chủ động hỗ trợ và test fan-out logout đến downstream RPs khi upstream logout; tùy sản phẩm, upstream logout và downstream logout có thể chỉ được hỗ trợ một phần. Nếu yêu cầu pháp lý bắt buộc global logout, đưa nó thành acceptance test, không dừng ở thử một nút Logout.

Đặc biệt khi dùng front-channel redirect, mạng/browser có thể không hoàn tất bước điều hướng. Với yêu cầu đáng tin cậy, xem xét back-channel logout, session revocation và khả năng retry/audit.

## 15. Security checklist cho multi-IdP broker

| Nguy cơ | Nguồn rủi ro | Kiểm soát bắt buộc |
| --- | --- | --- |
| Authorization-server mix-up | Broker đổi code tại token endpoint sai issuer | Lưu expected issuer trong state; dùng RFC 9207 `iss` khi hỗ trợ, hoặc distinct redirect policy |
| Login CSRF | Callback không gắn browser hoặc state bị tái sử dụng | State ngẫu nhiên, browser/session binding, one-time processing, nonce |
| Token substitution | Dùng upstream ID Token tại downstream client | Kiểm `iss/aud/azp` trên từng chặng; broker phát token mới |
| JWKS/key confusion | Tin key từ `jku`/`kid`/URL attacker cung cấp | Trust discovery/JWKS allowlisted, algorithm allowlist, cache/rotation đúng |
| SSRF qua discovery | User gửi `issuer-uri` bất kỳ | Admin-configured allowlist, DNS/IP/proxy controls, không dynamic fetch URL chưa tin |
| Open redirect | `redirect_uri` hoặc `returnTo` nhận từ query chưa validate | Exact redirect matching, allowlist, không echo user-supplied URL |
| Account takeover qua email | First login auto-link user trùng email | Identity linking có proof/admin approval, unique issuer+sub |
| Cross-tenant identity mix-up | Nhầm IdP B thành tenant A | Tenant/issuer mapping và membership/resource-level authorization |
| Weak upstream provider | Một IdP yêu cầu assurance thấp hơn policy | Policy per provider/action, không cho fallback âm thầm |
| Replay code/token | Auth request/callback bị lặp | PKCE, state/nonce, token exp và one-time redemption |
| Credential leakage | Token/secret trong log, URL, browser storage | Secure cookie, TLS, vault/HSM, redact logs, short TTL |
| Key rotation outage | Broker signing key đổi mà client cache JWKS cũ | Publish overlap, cache-aware rollover, negative tests |
| Logout inconsistency | Upstream logout không phát đến downstream | Session revocation/Back-Channel Logout và test từng adapter |
| Unsafe identity transformation | Broker nhận upstream `roles=admin` và tự phát admin | Mapping dựa trên allowlist/policy; do not infer |
| Multi-tab race | Hai upstream login diễn ra đồng thời | Tách state/nonce/request per transaction; tránh callback mix-up |
| Insecure reverse proxy | Client giả `X-Forwarded-Host`, sai scheme | Chỉ tin forwarded headers từ proxy được xác thực |

**Một broker có thể trở thành điểm rủi ro tập trung.** Khi bị xâm phạm signing private key hoặc session store, nhiều ứng dụng downstream bị ảnh hưởng. Cần HSM/secret storage, rotation, audit, blast-radius isolation giữa realms/tenants, HA và incident response.

## 16. Vận hành: discovery, keys, issuer và redirect

### 16.1. Discovery và issuer

Mỗi OIDC Provider có issuer ổn định. Ví dụ broker issuer:

```text
https://login.example.com/realms/partners
```

Với issuer này, một OIDC discovery endpoint phổ biến tương ứng là:

```text
https://login.example.com/realms/partners/.well-known/openid-configuration
```

Hãy lấy endpoint thực theo OIDC Discovery/metadata của broker. Kiểm:
- `issuer` trong discovery **khớp chính xác** issuer app cấu hình.
- `authorization_endpoint`, `token_endpoint`, `jwks_uri` dùng HTTPS và cùng trust boundary.
- `response_types_supported`/`grant_types_supported` đáp ứng authorization code flow.
- Public keys/JWKS tương ứng với token broker **đang ký**.
- `end_session_endpoint`/back-channel logout chỉ sử dụng khi broker công bố và hỗ trợ.
- Reverse proxy không thay `https` thành `http` hoặc expose host nội bộ trong metadata.

Khi thay FQDN/realm, issuer đổi có thể khiến toàn bộ downstream RP reject ID Token theo kiểm tra `iss` — đây là **migration thay trust**, không phải chỉnh DNS tùy tiện.

### 16.2. Key rotation

Broker có thể dùng signing key K_old và K_new theo giai đoạn:
1. Publish JWK mới khi vẫn phát token bằng K_old.
2. Đợi các RP/resource servers refresh key cache.
3. Bắt đầu ký bằng K_new, giữ public key cũ khi token cũ chưa hết hạn.
4. Kiểm tra signed tokens trên từng RP/API và thời hạn token/cache.
5. Retire K_old theo policy; nếu private key bị lộ, xử lý theo incident response thay vì giữ overlap dài.

Upstream IdP key rotation là chuyện **khác**, broker phải refresh JWKS của từng issuer và không chấp nhận key từ nguồn khác. Certificate SAML IdP và broker OIDC signing key cũng khác nhau.

### 16.3. Khả dụng và failure isolation

Một upstream IdP bị outage không nên kéo toàn bộ broker ngừng login cho các upstream còn lại, trừ khi policy/hạ tầng buộc. Cần:
- Timeout/circuit breaker cho metadata/JWKS/UserInfo.
- Cache metadata đúng TTL và key rotation, không bỏ signature validation khi fetch lỗi.
- Quotas/rate limits theo provider/tenant, isolation để một IdP chậm không hết thread pool.
- Health check broker, cache/session/database, audit pipeline.
- Fallback UX “IdP A đang không khả dụng”, không chuyển user sang IdP B nếu chưa có identity linking được chứng minh.
- Không log code, tokens, client secrets, cookie hoặc assertion.

## 17. Test matrix trước khi triển khai thật

| Ca kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| App login qua broker → IdP A | App nhận **broker issuer/sub**, không phải upstream token |
| App login qua broker → IdP B | Cùng downstream issuer, đúng account mapping theo upstream B |
| Upstream A/B cùng `sub=user-42` | Hai external identities riêng, không tự link |
| A/B cùng email nhưng khác `iss+sub` | Không gộp nếu thiếu proof/admin approval |
| User đổi email tại A, `sub` giữ nguyên | Cùng broker user |
| User đổi IdP với migration được duyệt | Link mới trỏ đúng broker user, audit đầy đủ |
| IdP mới chưa được allowlist | Broker không tự trust issuer URL từ query |
| Callback upstream với `state` sai | Reject, không đổi authorization code |
| Callback upstream issuer mix-up | Reject, không gửi code/secret sang token endpoint khác |
| Upstream ID Token sai `aud` | Reject dù chữ ký hợp lệ |
| Upstream ID Token sai `iss` | Reject, không map identity |
| Upstream ID Token hết hạn/nonce sai | Reject, không tạo broker session |
| Broker ID Token dùng làm API access token | Reject nếu API không cho đúng token type/audience |
| Broker token sai `aud` | Downstream app/API reject |
| JWT có `alg=none`/key không trong trust | Reject |
| Upstream claim `role=admin` | Không tự cấp admin tại app |
| Broker user DISABLED | Không phát phiên/token mới theo policy |
| Tenant membership bị thu hồi | API/app deny dù token cũ chưa hết hạn, theo revocation policy |
| First broker login với email trùng | Yêu cầu linking proof, không auto take over |
| Multi-tab upstream A/B callbacks đảo thứ tự | Không trộn client registrations và expected issuers |
| IdP C SAML signed assertion không hợp lệ | Broker reject, không phát OIDC token |
| SAML NameID transient | Không tự dùng làm identity key dài hạn |
| Broker signing key rotation | JWKS rollover có overlap, app validate đúng |
| Upstream key rotation | Broker refresh JWKS đúng issuer và reject key không tin |
| App local logout | Không tự hứa logout IdP upstream |
| Back-channel logout khi IdP hỗ trợ | Kiểm tra downstream sessions bị revocation đúng thiết kế |
| Upstream outage | Hiển thị lỗi riêng, không fallback sai identity |
| OIDC login sau proxy | Redirect URI, issuer và cookie đúng public HTTPS origin |
| Bảo mật logs | Không có raw token/secret/cookie, đủ correlation đã che |

**Các tầng test:** unit test cho mapping issuer+sub; Spring Security `oauth2Login` integration với OIDC test provider được kiểm soát; broker integration với upstream OIDC/SAML sandbox; browser e2e cho redirect/cookie/multi-tab; security negative cho token substitution, mix-up, account link takeover. Dùng test keys và dữ liệu giả; không đưa production tokens vào web decoder.

## 18. Quy trình đưa identity broker vào production

1. **Inventory:** lập danh sách apps, tenants, upstream issuers, giao thức, clients, algorithms, PKCE/redirect, tenant permissions và quy trình lifecycle.
2. **Chọn broker:** ưu tiên IAM có năng lực OIDC Provider + upstream federation, HA, MFA/step-up, audit và account linking; nếu tự xây, xác định rõ Authorization Server owner.
3. **Định nghĩa trust contract:** app tin issuer broker; broker tin từng upstream issuer/SP metadata; keys/redirect URIs chính xác, không trộn audiences.
4. **Định nghĩa identity mapping:** upstream issuer+sub hoặc SAML stable NameID; broker user ID bất biến; mapping to tenant; email không là khóa.
5. **Onboarding/linking:** first-login flow, invitation/SCIM, JIT có điều kiện, uniqueness/transaction; email match chỉ là tín hiệu đề xuất, không bằng chứng.
6. **Routing:** chính sách IdP được phê duyệt per tenant; login_hint/kc_idp_hint chỉ giúp UX, không tạo authority.
7. **Token policy:** thời hạn, signing JWKS, audience/scopes, refresh/revocation, bảo vệ client secrets, provenance và assurance mapping.
8. **Logout/deprovision:** lên thiết kế local/broker/upstream sessions, back-channel support và phản ứng user disable; không mặc định global SLO.
9. **Thử nghiệm:** test đa IdP, subject collision, token validation, mix-up, keys/redirect/SSRF, CSRF, step-up, outages.
10. **Rollout theo giai đoạn:** bắt đầu một app/IdP sandbox, canary tenants, theo dõi login success/error, audit, rollback và mapping migration.
11. **Vận hành lâu dài:** metadata/keys rotation, patch broker, backing DB/session/Redis, backup, alerting và incident response.

### Kiểm tra kiến thức

**Tại sao không chỉ cấu hình hai `ClientRegistration` trên portal rồi gọi đó là broker?** Vì khi đó portal là RP trực tiếp của hai IdP. Một broker thật phải có năng lực phát hành authorization codes/ID Tokens mới làm OP đối với các app downstream.

**Tại sao không dùng upstream `sub` làm downstream `sub`?** Vì namespace của `sub` gắn với issuer; có thể trùng giữa IdP và có thể pairwise theo RP. Broker cần broker subject được quản lý và mapping tin cậy.

**`email_verified=true` có đủ để tự liên kết hai tài khoản ở hai IdP?** Không. Email có thể tái cấp hoặc xác minh theo chính sách khác nhau. Linking cần proof/admin approval/contract và kiểm tra account đang sở hữu link.

**Nếu IdP A trả một token hợp lệ nhưng `aud` dành cho broker, app B có thể dùng token đó không?** Không. App B phải nhận token broker phát với audience của B hoặc dùng giao thức delegation/token exchange rõ ràng.

**Broker logout có đảm bảo logout mọi upstream và downstream không?** Không; cần hỗ trợ và kiểm thử cụ thể RP-initiated/logout front/back-channel hoặc SAML SLO, đồng bộ phiên và revocation.

## 19. Tài liệu chuẩn và hướng dẫn triển khai

1. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `iss`, `sub`, `aud`, `nonce`, ID Token validation, subject identifiers public/pairwise.
2. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): discovery, issuer metadata và JWKS.
3. [OAuth 2.0 Security Best Current Practice – RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html): PKCE, redirect exact matching, state, mix-up/issuer and token defense.
4. [OAuth 2.0 Authorization Server Issuer Identification – RFC 9207](https://www.rfc-editor.org/rfc/rfc9207.html): `iss` trong authorization response để chống mix-up khi có nhiều AS.
5. [Spring Security – Servlet OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) và [OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html): `oauth2Login`, ClientRegistration, OIDC RP.
6. [Spring Boot – OAuth2 Client configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): multiple client registrations, `issuer-uri`, default redirect URI.
7. [Spring Authorization Server – Social Login Guide](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-social-login.html): kết hợp Authorization Server và upstream OAuth2Login.
8. [Spring Security 7 – Authorization Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/index.html): Authorization Server/OP role, clients, issuer và ký token.
9. [Keycloak – Identity Brokering](https://www.keycloak.org/docs/latest/server_admin/#_identity_broker): upstream OIDC/SAML, first broker login, identity provider configuration và linking.
10. [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) và [Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html): phiên, logout và downstream propagation.
11. [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): CSRF, redirect, token validation và multi-AS threats.

**Kết luận:** triển khai identity broker là thiết lập **hai ranh giới xác thực độc lập**: broker xác minh các IdP bên ngoài và ánh xạ external identity vào broker user; các ứng dụng xác minh **token do broker phát** cho đúng issuer/audience. Thành công phụ thuộc vào việc phân tách issuer/sub, bảo vệ OAuth2 code+state+PKCE, không liên kết account chỉ bằng email, phân quyền tenant độc lập, kiểm soát token/keys và quản lý phiên/logout qua nhiều chặng.