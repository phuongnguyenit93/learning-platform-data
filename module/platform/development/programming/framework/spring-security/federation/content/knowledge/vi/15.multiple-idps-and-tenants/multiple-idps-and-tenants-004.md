# Ánh xạ domain, đường dẫn và tenant tới cấu hình đã được cho phép

> **Module:** Spring Security – federation. **Ngữ cảnh cha:** Nhiều IdP và tenant. Bài học tập trung vào cách biến hostname, đường dẫn và tenant do người dùng chọn thành **một `RelyingPartyRegistration` đã được quản trị phê duyệt**, đồng thời kiểm tra lại tenant sau khi SAML Response được xác thực. Ví dụ: **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x (Servlet)**. Khi dùng Spring Security 7.x, hãy kiểm tra lại các APIs và OpenSAML version; không sao chép nguyên mẫu cũ mà bỏ kiểm thử.

## 1. Mục tiêu và kiến thức cần biết

Sau bài, người học có thể:

1. Phân biệt **tenant nghiệp vụ**, **hostname/domain**, **đường dẫn của ứng dụng**, **registrationId của Spring Security**, **IdP entity ID**, **SP entity ID** và **Assertion Consumer Service (ACS)**.
2. Thiết kế bảng ánh xạ `(host, path tenant) → allowlisted registrationId` có **deny-by-default**, không nhận một URL metadata/IdP tùy ý từ browser.
3. Áp dụng Spring `RelyingPartyRegistrationRepository` để đăng ký nhiều cặp SP–IdP nhưng chỉ cho phép các liên kết đã phê duyệt hoạt động.
4. Kiểm soát cả **đường khởi tạo đăng nhập** (`/saml2/authenticate/{registrationId}`), **callback SAML** (`/login/saml2/sso/{registrationId}`) và **tài nguyên nghiệp vụ** sau khi xác thực.
5. Giải thích cách Spring chọn registration qua path, AuthnRequest đã lưu hoặc issuer gợi ý; vì sao dữ liệu đọc từ XML chưa xác minh không phải nguồn tin cậy.
6. Ràng buộc IdP issuer, signing certificate, SP entity ID/Audience, Destination/Recipient, `InResponseTo` và HTTP session với đúng tenant.
7. Ngăn **cross-tenant login**, **confused deputy**, **host-header poisoning**, **open redirect**, **SSRF từ metadata URL** và **identity collision** giữa IdP.
8. Viết Java 17 thực sự chạy được để thử ánh xạ, tích hợp Spring Security SAML với hai tenant, và lập ma trận kiểm thử âm.
9. Phân biệt **phép chọn IdP trước login** với **phân quyền truy cập tenant sau login**; cái sau không thể chỉ dựa vào query/path, tên miền hay email.

**Kiến thức đầu vào:** HTTP/HTTPS, Host và reverse proxy, path variables, Spring MVC, `SecurityFilterChain`, SAML `AuthnRequest`/`Response`/`Assertion`, `RelyingPartyRegistration`, Session và `SecurityContext`, IdP metadata và chữ ký XML.

## 2. Vấn đề: cùng một ứng dụng phục vụ nhiều IdP và tenant

Giả sử Portal phục vụ hai khách hàng doanh nghiệp **Acme** và **Beta**. Mỗi khách hàng có IdP riêng và cần cách đăng nhập riêng. Một thiết kế rõ ràng:

| Tenant nội bộ | Host public được phép | Đường dẫn bắt đầu login | Spring registrationId | IdP entity ID đã duyệt | SP entity ID | ACS đã đăng ký |
| --- | --- | --- | --- | --- | --- | --- |
| `acme` | `acme.portal.example.org` | `/t/acme/login` | `acme` | `https://idp.acme.example.org/saml` | `urn:portal:acme:sp` | `https://acme.portal.example.org/login/saml2/sso/acme` |
| `beta` | `beta.portal.example.org` | `/t/beta/login` | `beta` | `https://idp.beta.example.org/saml` | `urn:portal:beta:sp` | `https://beta.portal.example.org/login/saml2/sso/beta` |

Các địa chỉ là **ví dụ**, không phải IdP đang hoạt động. Trong tổ chức thật, IdP metadata, entity IDs, signing certificates, SP entity ID và ACS URL phải được quản trị theo bản ghi đối tác đã phê duyệt.

**Quy tắc:** Request trên `acme.portal.example.org/t/acme/login` có thể chuyển tới `registrationId=acme`; request trên `acme.portal.example.org/t/beta/login` phải **bị từ chối**, dù `beta` là registration có thật. Nếu chỉ nhìn path, attacker có thể chọn IdP ngoài tenant của hostname. Nếu chỉ nhìn Host, ứng dụng có thể bỏ qua tenant của path. Cần **kiểm cả hai** và định nghĩa rõ policy.

### 2.1. Những khái niệm KHÔNG đồng nghĩa

| Khái niệm | Là gì? | Có thể dùng làm gì? |
| --- | --- | --- |
| Tenant ID `acme` | Khóa nội bộ của miền dữ liệu và account trong ứng dụng | Authorization, identity linking, policy |
| Host `acme.portal.example.org` | Domain public của điểm vào ứng dụng | Gợi ý tuyến tenant nếu **được ingress/edge bảo vệ và kiểm allowlist** |
| Path `/t/acme/login` | Đường giao diện dùng để khởi tạo login | Input để chọn một tenant **trong danh sách đã duyệt** |
| Registration ID `acme` | Khóa Spring tra `RelyingPartyRegistration` | Chọn cặp SP/IdP cấu hình, không phải chứng cứ user thuộc tenant |
| IdP entity ID | `Issuer` của bên phát hành Response/Assertion | Ràng buộc trust của đúng IdP |
| SP entity ID | `AudienceRestriction/Audience` mà IdP cấp cho SP | Ràng buộc ứng dụng được quyền dùng Assertion |
| ACS | URL SP nhận SAMLResponse | Kiểm `Destination` và bearer `Recipient` |
| Metadata URI | Địa chỉ quản trị dùng nạp metadata IdP | Bootstrap cặp IdP/SP từ nguồn được cho phép, **không phải URL do user gửi** |
| NameID | Danh tính theo namespace/format của IdP | Identity link **sau khi signature và các điều kiện SAML hợp lệ** |
| `RelayState` | State tùy binding/flow | Hỗ trợ điều hướng/tương quan, không chứng minh tenant hoặc danh tính |

Một tenant có thể có **nhiều IdP được duyệt** theo migration, ví dụ `acme-primary` và `acme-backup`. Một IdP có thể phục vụ **nhiều tenant** nếu IdP thiết kế như vậy, nhưng application không được suy ra rằng mọi user từ IdP ấy đều thuộc mọi tenant. `registrationId` biểu diễn **cặp SP–IdP/trust configuration**, còn quyền nghiệp vụ thuộc mô hình account/tenant sau validation.

## 3. Hợp đồng ánh xạ phải có tính xác định và đóng

Đề xuất bảng cấu hình quản trị:

~~~text
ApprovedTenantRoutes
  (canonicalHost, tenantSlug) -> registrationId

  ("acme.portal.example.org", "acme") -> "acme"
  ("beta.portal.example.org", "beta") -> "beta"

ApprovedRegistrations
  "acme" -> {trusted IdP A, SP entityID A, ACS A, cert A,...}
  "beta" -> {trusted IdP B, SP entityID B, ACS B, cert B,...}

Mọi cặp (host, tenantSlug) không có trong bảng -> DENY
Mọi registrationId không có trong repository -> DENY
Mọi response không qua SAML validation -> DENY
Mọi principal không được phép truy cập tenant -> 403
~~~

### 3.1. Cái gì là dữ liệu do người dùng có thể tác động?

- `Host` HTTP và `X-Forwarded-Host` có thể bị spoof nếu reverse proxy không loại bỏ/ghi đè.
- `/t/{tenant}/login` do user chọn; `tenant` chỉ là **candidate**, không phải identity proof.
- Query parameter `?tenant=...`, `?idp=...`, `?metadataUrl=...` là hoàn toàn **untrusted**.
- SAML `Issuer`/`NameID`/`Attributes` trước khi xác minh chữ ký là dữ liệu do browser chuyển, cũng chưa đáng tin.
- `RelayState` và request ID chỉ có giá trị khi gắn với flow/session repository đúng.
- Header `X-Tenant-ID` do browser gửi không thể thay Identity/Authorization.
- SAMLResponse chứa `registrationId` trong URL ACS không tự chứng minh Response thuộc IdP đó.

**Nguyên tắc chọn:** Request có thể chỉ định **một khóa tra cứu ứng viên**, nhưng server phải chuyển khóa đó qua allowlist/repository rồi xác minh giao thức. Không bao giờ dựng `RelyingPartyRegistration` từ một URL tùy ý do user đưa.

### 3.2. Trước và sau authentication là hai cửa kiểm soát

~~~text
PRE-AUTH (request từ browser)
 Host + path tenant
        |
 canonicalize đúng chuẩn từ ingress tin cậy
        |
 exact allowlist route
        |
 registrationId đã có
        |
 RelyingPartyRegistrationRepository
        |
 Spring phát AuthnRequest đến IdP đã duyệt
        |
      IdP SSO
        |
      SAMLResponse
        |
 SAML signature/Issuer/Audience/Destination/
 Recipient/Conditions/InResponseTo validator
        |
 Saml2Authentication (authenticated)
        |
POST-AUTH (truy cập dữ liệu nghiệp vụ)
 trusted registrationId + identity link + tenant account
        |
 so khớp tenant của resource request
        |
 per-tenant authorization / row-level data isolation
        |
      ALLOW hoặc 403
~~~

**Nếu chỉ thực hiện PRE-AUTH**, tài khoản IdP A có thể truy cập nhầm tài nguyên tenant B bằng URL khác nếu tầng authorization không kiểm tenant. **Nếu chỉ thực hiện POST-AUTH**, ứng dụng có thể tạo AuthnRequest tới IdP/ACS không phù hợp, gây mix-up và UX không an toàn. Cần cả hai.

## 4. Mapping domain an toàn: không tin Host thô

Một hostname public có thể ánh xạ tới tenant khi hệ thống có một **ranh giới ingress** được bảo vệ: TLS certificates đúng, virtual host allowlist, traffic chỉ đi qua load balancer/reverse proxy được kiểm soát, backend không public trực tiếp và forwarded headers không thể bị client gắn bừa.

### 4.1. Luồng qua reverse proxy

~~~text
Browser -> TLS acme.portal.example.org
    |
Edge/Ingress:
  - Kiểm hostname thuộc danh sách host được triển khai
  - Kiểm TLS/SNI và chính sách public route
  - Xóa các X-Forwarded-* từ client ngoài
  - Tạo Forwarded/X-Forwarded-* mới theo request thật
  - Chỉ chuyển tới backend ứng dụng đã được phép
    |
Backend:
  - request.getServerName() theo canonical forwarding config
  - exact-match acme.portal.example.org trong allowlist
  - không tin giá trị "Host: evil.example" ngoài allowlist
~~~

Đặc biệt:

1. **Không** dùng `request.getHeader("X-Forwarded-Host")` trực tiếp làm tên tenant.
2. Nếu Spring cấu hình `server.forward-headers-strategy=framework` hoặc tương đương, trước đó phải bảo đảm edge **sanitize** headers và backend không thể truy cập trực tiếp. Bật trust headers trên backend public có thể tạo host-header poisoning.
3. Không nhận `evil-acme.portal.example.org` chỉ vì `endsWith("portal.example.org")`. Nếu dùng subdomain, cần chính sách exact canonical mapping; wildcard DNS/TLS không đồng nghĩa mọi tên là tenant được duyệt.
4. Port, scheme, chữ hoa/thường, Unicode/IDNA, trailing dot và dấu phân cách cần được chuẩn hóa theo **một policy duy nhất** tại ingress. Không tự loại bỏ các ký tự khác biệt để “chấp nhận gần đúng”.
5. Khi cần tenant ở cùng hostname, dùng **path allowlist** và cấu hình ACS/session tương ứng; đừng lấy host chung làm bằng chứng tenant.
6. Không biến bất kỳ domain do user tự gõ thành `baseUrl` để sinh SP entity ID, ACS hoặc URL IdP.

### 4.2. Vì sao không dùng subdomain extraction tùy ý?

Mẫu sai:

~~~java
// SAI: chỉ mô tả anti-pattern, không dùng ở production
String tenant = request.getServerName().split("\\.")[0];
String metadata = "https://" + tenant + ".example.com/saml/metadata";
// Nếu không có allowlist/trust, đường này cho attacker ảnh hưởng tenant/URL.
~~~

Dù hạn chế `tenant` là chữ-số, logic trên vẫn có thể kích hoạt tải metadata từ domain không được duyệt hoặc chọn tenant chưa onboard. Việc tự giải mã IP/Unicode, nối chuỗi vào URI và gọi network còn mở đường **SSRF** và nhầm domain. **Đúng:** host/path chỉ được dùng làm khóa để tra **registration có sẵn**, với metadata URI và cert đã được quản trị phê duyệt.

## 5. Mapping đường dẫn: chọn đúng candidate, không tạo open redirect

Đường `/t/{tenant}/login` có thể là một cách rõ ràng để tạo trải nghiệm đăng nhập cho từng tenant. Mẫu route:

| Host đã duyệt | Request | Quyết định |
| --- | --- | --- |
| `acme.portal.example.org` | `GET /t/acme/login` | 303 → `/saml2/authenticate/acme` |
| `beta.portal.example.org` | `GET /t/beta/login` | 303 → `/saml2/authenticate/beta` |
| `acme.portal.example.org` | `GET /t/beta/login` | 404/deny |
| `unregistered.portal.example.org` | `GET /t/acme/login` | 404/deny |
| `acme.portal.example.org` | `GET /t/ACME/login` | 404/deny trừ khi canonical alias đã duyệt |
| `acme.portal.example.org` | `GET /t/acme/login?idp=https://evil.example` | Chỉ dùng tuyến cố định acme; không dùng tham số `idp` |

**Không chuyển hướng tới URL do user gửi.** Redirect đích được dựng từ registrationId lấy từ bảng allowlist; ví dụ `/saml2/authenticate/acme` là **relative path nội bộ**, không phải `returnUrl`/`idpUrl` từ query. Với return-to URL sau login, chỉ cho phép relative paths/saved requests do server kiểm soát; tuyệt đối không lấy SAML `RelayState` làm open redirect chưa kiểm chứng.

### 5.1. Cảnh báo bypass đường chọn đăng nhập

Một lỗi tinh vi: controller `GET /t/{tenant}/login` có allowlist hoàn hảo, nhưng Spring Security mặc định vẫn mở trực tiếp:

~~~text
GET /saml2/authenticate/{registrationId}
GET /saml2/authenticate?registrationId=...
~~~

Nếu user đang ở host Acme và gọi trực tiếp `/saml2/authenticate/beta`, họ có thể **bỏ qua controller chọn tenant**. Spring Security vẫn có thể xác thực đúng registration Beta; tuy nhiên trải nghiệm, route policy và các giả định tenant có thể sai. Bởi vậy, **guard endpoint sinh AuthnRequest** theo host/registration, hoặc định nghĩa custom `Saml2AuthenticationRequestResolver` sử dụng cùng allowlist, đồng thời kiểm tra post-auth tenant.

Ví dụ ở mục 9 dùng **filter chặn trực tiếp cả dạng path và query không được cho phép**, thay vì chỉ bảo vệ controller. Với production tùy biến phức tạp, có thể đặt quyết định tenant trong `RelyingPartyRegistrationResolver`/`AuthenticationConverter` và request resolver được kiểm thử theo đúng Spring Security version.

## 6. RelyingPartyRegistration: trust configuration, không phải dữ liệu nhập tự do

Spring Security biểu diễn một cặp SP/IdP bởi `RelyingPartyRegistration`. Nó bao gồm tối thiểu:

- `registrationId` – khóa nội bộ, phải duy nhất.
- SP `entityId` – audience mà IdP sử dụng trong Assertion.
- SP `assertionConsumerServiceLocation` – ACS/destination và bearer recipient.
- IdP `entityId` – asserting party issuer, từ metadata đáng tin.
- IdP SSO URL, bindings, verification credentials (public signing cert).
- SP signing/decryption credentials nếu profile/hợp đồng yêu cầu.
- SLO metadata/credentials nếu dùng Single Logout.

Một `RelyingPartyRegistrationRepository` chứa các configurations được duyệt. `InMemoryRelyingPartyRegistrationRepository` phù hợp với số tenant cố định; hệ thống lớn có thể dùng DB cấu hình với approval/versioning/caching. Nhưng database không biến metadata bất kỳ thành tin cậy: onboarding và refresh vẫn phải được kiểm soát.

### 6.1. Không nhầm Spring `registrationId` với Issuer

Ví dụ:

~~~text
registrationId="acme"                        (Spring key)
IdP entity ID="https://idp.acme.example/saml" (trusted Issuer)
SP entity ID="urn:portal:acme:sp"              (Audience)
ACS="https://acme.portal.example.org/login/saml2/sso/acme"
~~~

Một SAMLResponse có `Issuer=IdP Beta` nhưng đến `/login/saml2/sso/acme` không được coi là hợp lệ vì URL chứa acme. Provider phải kiểm chữ ký/issuer bằng **IdP A verification certificates**, audience/recipient/destination theo **SP A registration** và request correlation. Nếu sai, từ chối.

Một response ký bởi IdP Acme nhưng có `Audience=urn:portal:beta:sp` cũng phải bị từ chối tại Acme. **Signature hợp lệ chưa đủ**.

### 6.2. Default lookup và custom lookup

Trong Spring Security 6.5, `Saml2AuthenticationTokenConverter` có thể tìm registration từ một AuthnRequest đã lưu hoặc `registrationId` trong request URI; khi không tìm được, có thể dùng `Response/Issuer` như **hint** để tìm một registration đã tồn tại. Phần đọc XML issuer **chưa chứng minh đã được IdP ký**; chỉ OpenSAML provider sau validation mới thiết lập kết quả authenticated.

Nếu hệ thống có nhiều IdP dùng cùng Issuer trong các môi trường khác nhau hoặc hai registrations có issuer trùng, việc suy ra từ Issuer có thể **mơ hồ**. Dùng đường callback có registrationId rõ, session request state và custom `AuthenticationConverter`/resolver nếu thực sự cần; luôn so khớp với approved repository. Không tự tạo IdP trust mới khi thấy Issuer lạ.

### 6.3. Phiên SP-initiated và `InResponseTo`

~~~text
Host Acme + /t/acme/login
  -> allowlist: registration acme
  -> AuthnRequest ID="_req-acme-42", Issuer SP Acme
  -> lưu AuthnRequest + registration trong repository/session
  -> browser tới IdP Acme

IdP Acme:
  -> SAMLResponse InResponseTo="_req-acme-42"
  -> POST https://acme.portal.example.org/login/saml2/sso/acme

SP Acme:
  -> tìm request đã lưu, so InResponseTo
  -> verify signature bằng IdP Acme cert
  -> verify Issuer, Audience, Destination, Recipient, Conditions
  -> tạo Saml2Authentication với registrationId=acme
~~~

Không dùng `RelayState` hay cookie không ký độc lập để chọn tenant cuối cùng. State của browser có thể giúp tìm request, nhưng SAML Response vẫn phải đi qua cryptographic/protocol validations. Nếu session bị mất ở callback vì SameSite, proxy hoặc load balancer, **không bỏ InResponseTo** để chạy bằng mọi giá.

### 6.4. SP-initiated khác IdP-initiated

**IdP-initiated SSO** có thể không có AuthnRequest trước đó. Khi nhiều tenant, nó còn rủi ro nhầm issuer hoặc login CSRF nếu SP không có state/correlation mạnh. Nếu sản phẩm không cần, **cấm unsolicited SAMLResponse** theo policy; trong ví dụ ở mục 9, endpoint ACS không có registrationId bị guard từ chối, nhưng đó **không tự thay thế** các chính sách hạn chế unsolicited SSO trên endpoint có registrationId. Cần kiểm chứng hành vi `Saml2AuthenticationRequestRepository` và validator theo Spring Security version, IdP binding và yêu cầu an toàn. Không tuyên bố chỉ một filter check path đã cấm hoàn toàn IdP-initiated login.

## 7. Định danh người dùng và phân quyền sau khi SAML xác thực

Một response SAML có chữ ký/issuer/audience chính xác chứng minh một principal theo IdP. Nó **chưa tự chứng minh** người đó được xem data của tenant nào, nhất là khi một IdP phục vụ nhiều tenant hoặc có account/email trùng.

### 7.1. External identity key phù hợp

Thay vì chỉ dùng:

~~~text
key = NameID
hoặc key = email
~~~

hãy thiết kế mô hình:

~~~text
Trusted IdP entity ID
  + approved registration/tenant context
  + NameID format/qualifiers/value (theo hợp đồng IdP)
       |
       v
ExternalIdentityKey
       |
       +--> IdentityLink(existing internal_user_id, tenant_id)
                      |
                      +--> UserStatus=ACTIVE?
                      +--> Tenant membership enabled?
                      +--> Allowed group/role mapping?
                      |
                      v
               Authorization for resource
~~~

Với NameID kiểu transient, không dùng làm khóa tài khoản lâu dài. Email có thể đổi, tái cấp hoặc trùng giữa IdP; **không tự liên kết accounts giữa tenant bằng email**. Nếu sử dụng IdP attributes cho role mapping, chỉ dùng attributes đã được bảo vệ/kiểm chứng và cấu hình mapping theo đối tác đã phê duyệt.

### 7.2. RegistrationId là điều kiện cần, chưa đủ

Trong ví dụ dưới, endpoint `/t/acme/me` kiểm tra `principal.getRelyingPartyRegistrationId() == "acme"` như một **guard minh họa** để tránh truy cập chéo registration. Nhưng trong sản phẩm thật, còn phải kiểm **identity link tới tenant Acme**, user còn hoạt động, quyền xem resource và row-level data filters.

Ví dụ một principal từ Acme có thể authenticated thành công rồi cố truy cập:

~~~text
GET https://beta.portal.example.org/t/beta/reports
~~~

Nếu server chỉ kiểm `authenticated()` và không so tenant của principal/account, hệ thống có nguy cơ **cross-tenant data exposure**. Tầng authorization cho API/services/data phải kiểm tenant một cách nhất quán, không chỉ một endpoint demo.

## 8. Kiểm tra domain, path và tenant trên toàn bộ vòng đời

| Giai đoạn | Giá trị có thể tin sau kiểm chứng | Phải kiểm | Không được |
| --- | --- | --- | --- |
| HTTP ingress | Host/scheme do trusted edge xác lập | Host allowlist, TLS, canonical public routes | Tin raw forwarded header không kiểm soát |
| Tenant picker/login | `(host, pathTenant)` thuộc allowlist | Mapping ra registration có thật | Dựng metadata URL từ tenant string |
| Direct AuthnRequest endpoint | RegistrationId từ URL/query | Host–registration binding/guard | Bỏ qua picker để chuyển sang tenant khác |
| AuthnRequest | RP registration, SP entity ID, ACS | IdP destination, signing, stored request | Dùng issuer/key từ user input |
| ACS callback | Registration ứng viên + request state | Signature, issuer, audience, destination, recipient, timing | Tin URL callback là đủ |
| Authentication result | `Saml2Authentication` sau provider validation | Trusted registrationId, principal, attributes | Cấp user internal chỉ bằng NameID/email |
| Business API | Internal identity link + tenant + authorities | Tenant membership và resource ownership | Chỉ kiểm `isAuthenticated()` |
| Metadata publication | Approved registration & public cert | Host/ACS/Entity ID đúng deployment | Công bố metadata dựng từ arbitrary Host |
| SLO | Principal/session registration đã xác thực | Đúng IdP, signed LogoutRequest/Response, correlation | Logout cross-tenant bằng query idp |

**Mỗi bước phải fail-closed**, không chọn một “default IdP” mơ hồ khi không rõ tenant. Nếu hỗ trợ tenant picker, trang picker nên liệt kê **chỉ tenants/IdPs user được phép thấy**; hành động chọn vẫn phải revalidate ở server.

## 9. Ví dụ hoàn chỉnh: Java 17 + Spring Boot 3.5 + 2 IdP đã duyệt

Ví dụ này cố ý dùng **hai host public cố định** cùng hai tenant. Java code tạo hai `RelyingPartyRegistration` từ metadata URIs **được hardcode như nguồn quản trị của môi trường demo**. Bộ route không lấy IdP URL hoặc cert từ request. Nó bảo vệ:

1. `GET /t/{tenant}/login` – chọn registration chỉ qua map `(host, tenant)`.
2. `GET /saml2/authenticate/{registrationId}` – chặn direct access sang registration của host khác.
3. `POST /login/saml2/sso/{registrationId}` – chặn ACS path trên host khác (OpenSAML vẫn phải kiểm response).
4. `GET /t/{tenant}/me` – đối chiếu registration đã authenticated với tenant của resource.

**Lưu ý:** Đây là demo hướng dẫn cấu trúc routing. Chạy SAML thật cần metadata IdP có thật, IdP app registration, TLS/DNS public host, HTTP sessions hợp lệ và signing/decryption credentials nếu IdP yêu cầu. Nếu chạy trực tiếp trên `localhost`, host allowlist sẽ từ chối – đó là hành vi **đúng với policy đã mô tả**. Dùng hostnames test có DNS/TLS phù hợp hoặc điều chỉnh bảng cấu hình cho sandbox; không tắt guard ở production.

### 9.1. Cấu trúc

~~~text
saml-tenant-router/
├── pom.xml
└── src/main/
    ├── java/demo/TenantSamlApplication.java
    └── resources/application.yml
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>saml-tenant-router</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots><enabled>false</enabled></snapshots>
    </repository>
  </repositories>
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
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 9.3. application.yml

~~~yaml
server:
  port: 8080
  forward-headers-strategy: none
~~~

Ở demo, ứng dụng nhận canonical host qua ingress hoặc test client; không tùy tiện tin forwarded headers. Nếu deployment dùng reverse proxy cần forwarded host/scheme, cấu hình forwarding **chỉ sau khi proxy xóa và tự cấp headers đúng** và backend chỉ nhận kết nối từ proxy. Trong môi trường nhiều host, không lấy base URL động từ request để thay các entity ID/ACS cố định.

### 9.4. src/main/java/demo/TenantSamlApplication.java

~~~java
package demo;

import java.io.IOException;
import java.net.URI;
import java.util.Locale;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.saml2.provider.service.web.Saml2WebSsoAuthenticationRequestFilter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class TenantSamlApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantSamlApplication.class, args);
    }

    // Host và tenant đều là khóa tra cứu vào bảng APPROVED, không phải
    // nơi để ứng dụng nối thành IdP metadata URL do client điều khiển.
    record RouteKey(String host, String tenant) {}
    record TenantRoute(String tenant, String registrationId) {}

    private static final Map<RouteKey, TenantRoute> APPROVED = Map.of(
        new RouteKey("acme.portal.example.org", "acme"),
            new TenantRoute("acme", "acme"),
        new RouteKey("beta.portal.example.org", "beta"),
            new TenantRoute("beta", "beta")
    );

    static String canonicalHost(HttpServletRequest request) {
        // Chỉ có ý nghĩa khi trusted ingress kiểm soát Host/forwarded headers.
        return request.getServerName().toLowerCase(Locale.ROOT);
    }

    static TenantRoute route(HttpServletRequest request, String tenant) {
        TenantRoute result =
            APPROVED.get(new RouteKey(canonicalHost(request), tenant));
        if (result == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Unapproved tenant route");
        }
        return result;
    }

    static boolean allowedRegistration(String host, String registrationId) {
        return APPROVED.entrySet().stream().anyMatch(entry ->
            entry.getKey().host().equals(host) &&
            entry.getValue().registrationId().equals(registrationId));
    }

    @Bean
    RelyingPartyRegistrationRepository registrations() {
        // Metadata locations phải do quản trị phê duyệt.
        // Phải thay các example URLs bằng sandbox IdP thực tế.
        RelyingPartyRegistration acme =
            RelyingPartyRegistrations
                .fromMetadataLocation("https://idp.acme.example.org/metadata")
                .registrationId("acme")
                .entityId("urn:portal:acme:sp")
                .assertionConsumerServiceLocation(
                    "https://acme.portal.example.org/login/saml2/sso/acme")
                .build();

        RelyingPartyRegistration beta =
            RelyingPartyRegistrations
                .fromMetadataLocation("https://idp.beta.example.org/metadata")
                .registrationId("beta")
                .entityId("urn:portal:beta:sp")
                .assertionConsumerServiceLocation(
                    "https://beta.portal.example.org/login/saml2/sso/beta")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(acme, beta);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/t/*/login").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            // Guard nằm trước filter tạo AuthnRequest.
            // Nó không thay thế signature/audience validation.
            .addFilterBefore(
                new HostRegistrationGate(),
                Saml2WebSsoAuthenticationRequestFilter.class)
            .build();
    }

    // Guard direct Spring endpoints: controller picker KHÔNG phải
    // lối vào duy nhất; endpoint mặc định vẫn có thể được gọi trực tiếp.
    static class HostRegistrationGate extends OncePerRequestFilter {
        private static final String AUTH = "/saml2/authenticate/";
        private static final String ACS = "/login/saml2/sso/";

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            String host = canonicalHost(request);
            String uri = request.getRequestURI();
            String contextPath = request.getContextPath();
            String path = uri.substring(contextPath.length());

            // Không cho dùng query-only registrationId hoặc ACS không rõ
            // registration trong demo SP-initiated strict routing này.
            if (path.equals("/saml2/authenticate") ||
                path.equals("/login/saml2/sso")) {
                response.sendError(HttpServletResponse.SC_NOT_FOUND);
                return;
            }

            String registrationId = null;
            if (path.startsWith(AUTH)) {
                registrationId = path.substring(AUTH.length());
            } else if (path.startsWith(ACS)) {
                registrationId = path.substring(ACS.length());
            }

            if (registrationId != null &&
                (registrationId.isBlank() ||
                 registrationId.contains("/") ||
                 !allowedRegistration(host, registrationId))) {
                response.sendError(HttpServletResponse.SC_NOT_FOUND);
                return;
            }

            chain.doFilter(request, response);
        }
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String index() {
            return "Use /t/acme/login or /t/beta/login on approved hosts";
        }

        @GetMapping("/t/{tenant}/login")
        ResponseEntity<Void> login(
                @PathVariable String tenant,
                HttpServletRequest request) {
            TenantRoute approved = route(request, tenant);
            // URI cố định theo allowlist; không dùng redirectUrl do user gửi.
            return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create(
                    "/saml2/authenticate/" + approved.registrationId()))
                .build();
        }

        @GetMapping("/t/{tenant}/me")
        ResponseEntity<Map<String, String>> me(
                @PathVariable String tenant,
                HttpServletRequest request,
                Authentication authentication) {

            TenantRoute approved = route(request, tenant);

            if (!(authentication instanceof Saml2Authentication saml) ||
                !(saml.getPrincipal() instanceof Saml2AuthenticatedPrincipal p) ||
                !approved.registrationId()
                    .equals(p.getRelyingPartyRegistrationId())) {
                return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(Map.of("error", "Tenant registration mismatch"));
            }

            // Demo chỉ xác minh registration. Production PHẢI kiểm tra
            // IdentityLink, trạng thái user, tenant membership, roles.
            return ResponseEntity.ok(Map.of(
                "tenant", approved.tenant(),
                "registrationId", approved.registrationId()));
        }
    }
}
~~~

### 9.5. Giải thích mã

- `APPROVED` giữ các cặp `(canonicalHost, tenant)` và registrationId đã phê duyệt. Không có fallback. `GET /t/evil/login` hoặc `Host=evil.example` không tìm được route, phản hồi 404.
- `RelyingPartyRegistrations.fromMetadataLocation(...)` nạp metadata IdP đã được **chọn trước trong cấu hình**. Các metadata URIs trong demo là ví dụ; sản phẩm phải dùng URL IdP thật được phê duyệt, kiểm provenance, certificate rollover và network access theo policy.
- `entityId(...)` là SP entity ID khác nhau cho Acme/Beta; `assertionConsumerServiceLocation(...)` cố định public HTTPS callback đúng host/registration. Phải đăng ký những giá trị này ở IdP tương ứng.
- `SecurityFilterChain` chỉ permitAll đường login picker, không cho phép các API nghiệp vụ nếu chưa authenticated.
- `HostRegistrationGate` chặn **cách gọi trực tiếp** `/saml2/authenticate/beta` trên host Acme, và chặn `/login/saml2/sso/beta` trên host Acme. Nó cũng chặn dạng route không rõ registrationId để giảm mơ hồ trong demo. Filter không thay thế SAML signature validation.
- `/t/{tenant}/me` kiểm tra **registrationId của principal đã xác thực** phải bằng registration của route đang xem. Nếu không, 403. Không trả `NameID`, attributes hay raw SAMLResponse trong response demo.
- Để bảo vệ toàn ứng dụng thật, cần áp **tenant authorization ở service/data layer**; controller demo không tự tạo row-level security.
- Trong cluster, AuthnRequest repository/session phải hoạt động xuyên node, và ingress cần giữ canonical host. Nếu login khởi đầu ở Acme nhưng callback chuyển sang Beta, `HostRegistrationGate` từ chối.
- `getServerName()` được dùng vì application giả định edge đã xử lý trust boundary. Nếu backend public trực tiếp hoặc Host/forwarded headers không được bảo vệ, **điều kiện mẫu chưa đủ an toàn**. Đó là yêu cầu triển khai, không phải chức năng Java tự đảm bảo.
- Cách viết dùng tính năng `record` và pattern matching `instanceof` của Java 17. Không cần tạo custom SAML AuthenticationProvider hay tự parse XML.

### 9.6. Cài đặt và chạy có kiểm soát

Đầu tiên, tích hợp **hai IdP sandbox** và đăng ký tại từng IdP:
 
~~~text
Acme:
  IdP metadata = URL thật đã duyệt
  SP entity ID = urn:portal:acme:sp
  ACS = https://acme.portal.example.org/login/saml2/sso/acme

Beta:
  IdP metadata = URL thật đã duyệt
  SP entity ID = urn:portal:beta:sp
  ACS = https://beta.portal.example.org/login/saml2/sso/beta
~~~

Nếu IdP yêu cầu signed AuthnRequest, phải cấu hình SP signing private key và public certificate tương ứng từ secret store. Nếu IdP phát EncryptedAssertion, thêm decryption credentials của **SP**. Không đưa IdP private key vào ứng dụng. Nếu metadata của IdP không truy cập được, bean registration có thể fail lúc startup; đừng coi việc dùng URL mẫu là đã chạy login.

Chạy Java 17 và Maven:

~~~bash
mvn spring-boot:run
~~~

Sau khi DNS/TLS/Ingress sandbox phục vụ hai public host, mở:

~~~text
https://acme.portal.example.org/t/acme/login
https://beta.portal.example.org/t/beta/login
~~~

Ứng dụng redirect 303 đến generator tương ứng; Spring Security tạo AuthnRequest và chuyển tới IdP đúng registration. Nếu User login hợp lệ, có thể gọi:

~~~text
https://acme.portal.example.org/t/acme/me
https://beta.portal.example.org/t/beta/me
~~~

Output JSON của Acme sau SAML login đúng sẽ có dạng:

~~~json
{"tenant":"acme","registrationId":"acme"}
~~~

Output này **phụ thuộc SAML login thật**, không xuất hiện khi URL metadata mẫu chưa được thay, khi trình duyệt thiếu session/correlation hoặc validation fail. Ngay cả khi JSON xuất hiện, trong production vẫn cần truy vấn IdentityLink và tenant entitlement.

### 9.7. Giới hạn cố ý của sample

1. Sample chỉ có **một IdP trên một tenant**; nhiều IdP/tenant cần bảng định tuyến có thêm `idpChoice` được allowlist và UX phù hợp.
2. Sample chưa có persistence cho tenant membership, user status, roles, SCIM provisioning hoặc DB row-level filters; phải bổ sung trước production.
3. Sample không đăng ký SP metadata endpoint; nếu IdP cần metadata tự động, bật `.saml2Metadata(Customizer.withDefaults())` và **review khả năng liệt kê toàn bộ registrations/hostname metadata** cùng chính sách expose metadata, bảo đảm entity ID/ACS chính xác.
4. Callback `/login/saml2/sso/{registrationId}` nhận response qua filter Spring Security; **signature/issuer/audience/recipient/time/correlation** do provider/validator cần được kiểm tra đúng phiên bản. Host gate là kiểm soát bổ sung.
5. Sample chặn dạng query-only AuthnRequest, nhưng các đường dẫn/gateway tùy biến trong production phải được rà soát đầy đủ để không có alias bypass; đừng tuyên bố filter mẫu thay thế firewall/ingress policy.
6. Sample không thiết kế IdP-initiated SSO; nếu cần, phải đánh giá login CSRF, replay, đăng ký route và sự thiếu `InResponseTo` với đúng Spring Security version.
7. Nếu muốn thử localhost, cần có route test explicit phù hợp IdP sandbox, không bỏ canonical-host checks trong bản production.
8. Ví dụ `RelyingPartyRegistrations.fromMetadataLocation` được dùng để có full metadata. Nếu onboarding metadata động, xử lý theo mục 11; **không** nối host/tenant string vào URL IdP.

## 10. Chương trình Java 17 độc lập: kiểm allowlist và stdout

Trước khi tích hợp SAML, ta có thể kiểm chính sách mapping như một hàm thuần Java. Chương trình dưới **có thể chạy bằng JDK 17 không cần Spring, Maven hoặc IdP**, và cho thấy host + tenant mới chọn được một registration.

**Tệp `TenantRouteDemo.java`:**

~~~java
import java.util.Map;

public class TenantRouteDemo {

    record RouteKey(String host, String tenant) {}

    private static final Map<RouteKey, String> APPROVED = Map.of(
        new RouteKey("acme.portal.example.org", "acme"), "acme",
        new RouteKey("beta.portal.example.org", "beta"), "beta"
    );

    static String resolve(String host, String tenant) {
        // host ở đây được giả định đã canonical từ trusted ingress;
        // string bất kỳ không tự chứng minh tính chính hãng của network.
        String registration = APPROVED.get(new RouteKey(host, tenant));
        return registration == null ? "DENY" : registration;
    }

    static void check(String host, String tenant) {
        System.out.println(host + " /t/" + tenant +
                "/login -> " + resolve(host, tenant));
    }

    public static void main(String[] args) {
        check("acme.portal.example.org", "acme");
        check("beta.portal.example.org", "beta");
        check("acme.portal.example.org", "beta");
        check("attacker.example.org", "acme");
        check("acme.portal.example.org", "ACME");
        check("beta.portal.example.org", "../acme");
    }
}
~~~

Chạy:

~~~bash
javac TenantRouteDemo.java
java TenantRouteDemo
~~~

**Stdout chính xác:**

~~~text
acme.portal.example.org /t/acme/login -> acme
beta.portal.example.org /t/beta/login -> beta
acme.portal.example.org /t/beta/login -> DENY
attacker.example.org /t/acme/login -> DENY
acme.portal.example.org /t/ACME/login -> DENY
beta.portal.example.org /t/../acme/login -> DENY
~~~

**Giải thích:** `Map.get` với cặp key dùng exact match, không tìm được thì `DENY`. Trường hợp `../acme` trong demo là chuỗi test thuần Java; trong HTTP thật, browser/proxy/framework có thể normalize path hoặc từ chối từ trước, vì vậy không dùng kết quả demo làm bằng chứng chống path traversal ở ingress. Luôn kiểm các đường dẫn đã normalize và route matching thực tế trong integration tests.

**Đừng sử dụng `resolve(...)` để tự khẳng định user authenticated hay authorized.** Nó chỉ chọn registration candidate. SAML response vẫn cần cryptographic verification; resource authorization vẫn cần identity link và tenant membership.

## 11. Onboarding tenant/IdP mới: quy trình thay đổi cấu hình được phép

Một hệ thống SaaS có thể thêm tenant thường xuyên, nhưng **dynamic tenant** không đồng nghĩa “mỗi URL metadata client đưa tới đều đáng tin”. Một quy trình chuẩn:

1. **Business approval:** xác định tenant nội bộ, owner, hợp đồng với đối tác IdP, trạng thái onboarding và domains được phép.
2. **Domain ownership:** xác minh chứng minh quyền kiểm soát domain/hostname theo policy; thiết lập TLS và ingress route chính xác, tránh hijack tenant cũ.
3. **Metadata provenance:** quản trị viên hoặc service onboarding được cấp quyền nạp metadata từ **nguồn được xác nhận trước**; khóa hostname/URL chính xác hoặc allowlist endpoint; chặn redirect sang IP nội bộ, link-local, metadata service hoặc scheme không được phép.
4. **Cryptographic trust:** xác nhận IdP entity ID, public signing certificates, algorithms và SSO endpoint; không dùng cert lấy từ SAMLResponse chưa verify.
5. **SP registration:** gán registrationId unique, SP entity ID, ACS/SLO URLs và signing/decryption credentials nếu yêu cầu. Tránh reuse entity ID sai tenant và tránh collision callback.
6. **Mapping approval:** commit/persist chính xác tuple `(canonicalHost, tenantSlug, registrationId)`; kiểm tra reference tới approved registration tồn tại. Chỉ trạng thái `ACTIVE` mới được phục vụ login.
7. **Test staging:** SP-initiated flow, signed response, issuer/audience/destination/time/correlation, authnrequest request state, cookie và negative cross-tenant tests.
8. **Publish/rollout:** deploy ingress/DNS/cert, metadata/trust, app mapping và identity linking theo thứ tự; có rollback/feature flag, không bật wildcard mặc định.
9. **Monitor:** login success/failure theo registration, unknown host/route, issuer mismatch, signature failure, audience/ACS mismatch, session/correlation missing.
10. **Decommission:** ngừng cấp AuthnRequest mới, thu hồi account links/tokens/sessions theo policy, xóa registration từ allowlist, gỡ IdP trust keys khi an toàn và xử lý domain reassignment.

### 11.1. Database-backed repository

Nếu có hàng trăm IdP, cấu hình được lưu tại DB (hoặc cấu hình dịch vụ) thay vì Java Map. Lúc đó:

~~~text
Table tenant_route:
  canonical_host
  tenant_slug
  registration_id
  status (ACTIVE/INACTIVE)
  approved_by
  version

Table relying_party_config:
  registration_id
  trusted_idp_entity_id
  trusted_metadata_source
  sp_entity_id
  public_acs_uri
  verification_key_refs
  signing_key_refs (secret reference only)
  status
  version
~~~

Chỉ người/pipeline có quyền onboarding mới sửa bảng; runtime chỉ đọc các bản ghi `ACTIVE`. Mọi cập nhật metadata/keys phải qua validation, audit và rollback. `registrationId` khi resolve ra repository có thể cache theo version; khi revoke tenant/key cần định nghĩa invalidation. Không chấp nhận tùy tiện một record chỉ vì nó tồn tại trong DB hoặc do người dùng tự thêm.

### 11.2. Kỹ thuật chống SSRF lúc nạp metadata

- Không nhận `?metadataUrl=...` hoặc `X-IdP-URL` từ end-user request.
- Chỉ scheme/host/port đã được phê duyệt; thông thường HTTPS; TLS certificate verification đầy đủ.
- Ngăn SSRF qua DNS rebinding, redirects tới private/link-local IP, IPv6 local targets, cloud metadata endpoints và userinfo trong URI bằng policy egress/network và validation tại backend.
- Dùng metadata đã được snapshot/approved hoặc distribution backend được kiểm soát nếu live metadata refresh có rủi ro.
- Hạn chế kích thước, content type và parser; theo dõi định kỳ certificate rotation và phát hiện metadata bị thay bất ngờ.
- **Không** coi việc một URL trả về XML hợp lệ nghĩa là IdP được tin.

## 12. Các tình huống phức tạp cần xử lý

### 12.1. Một tenant nhiều IdP

Acme có IdP chính và IdP dự phòng:

~~~text
tenant=acme
  -> registrationId=acme-main
  -> registrationId=acme-backup
~~~

Đừng lấy `?idp=any-url`; chỉ cho `idpChoice` chọn **một registrationId thuộc allowlist của Acme**. Việc cho phép backup phải được duyệt, đặc biệt nếu signing cert hoặc issuer thuộc hệ thống khác. Nếu user từ hai IdP cùng có email giống nhau, không auto-link accounts; cần identity-link policy và kiểm duyệt.

### 12.2. Một IdP phục vụ nhiều tenant

Hai tenant có cùng IdP entity ID, nhưng SP có thể có entity ID/ACS khác nhau. Khi đó đọc `Response/Issuer` không đủ để biết tenant, vì **Issuer trùng nhau**. Phải dựa trên SP-initiated request correlation, đúng registration và kiểm `Audience`/`Recipient`/`Destination`; sau xác thực vẫn phải kiểm identity link tới tenant.

### 12.3. Tenant theo path trên một host chung

Ví dụ `portal.example.org/t/acme/login` và `portal.example.org/t/beta/login`. Được phép nếu có **route allowlist**, nhưng cần quyết định nơi nhận ACS: có thể dùng `/login/saml2/sso/acme` và `/login/saml2/sso/beta` trên cùng host, với hai registration khác nhau. Không dùng path tenant tùy ý để dựng metadata IdP. SAML provider vẫn kiểm audience/recipient; business resource phải đối chiếu registration và tenant.

**Cảnh báo phiên dùng chung cookie trên một host:** Người dùng có thể lần lượt đăng nhập vào Acme và Beta trong cùng browser session; một `SecurityContext` có thể được thay bởi authentication mới. Nếu cần **đồng thời hai identity/tenant sessions**, phải thiết kế isolation rõ (subdomains, session partitioning hoặc tenancy-aware session model), không cho rằng chỉ đổi path tạo hai phiên độc lập.

### 12.4. Tenant alias và custom domains

Một khách hàng có `company.example.com` và `acme.portal.example.org` cùng dẫn tới Acme. Cả hai domain phải được duyệt và ánh xạ rõ tới registration/tenant. SAML `Destination`/`Recipient` và IdP ACS có thể cần một **canonical callback URL duy nhất**, vì AuthnRequest khởi đầu từ alias nhưng browser callback về canonical host có thể **mất session cookie**. Thiết kế SSO entrypoint redirect sang canonical host **trước khi bắt đầu AuthnRequest**, hoặc có cross-domain state handoff an toàn do server quản lý. Không thêm mọi custom domain như ACS wildcard tùy ý.

### 12.5. Proxy thay scheme hoặc host

Browser đến `https://acme.portal.example.org`; backend thấy `http://app:8080`. Nếu SP tạo `{baseUrl}` dựa trên host sai, IdP có thể phát assertion dành cho ACS nội bộ. Với tenant đã duyệt, nên khai báo **public entity ID/ACS cố định** hoặc sử dụng forwarded headers từ proxy đã tin. Không bỏ Destination check để chữa proxy; chỉnh ingress, SP metadata và IdP registration.

### 12.6. Di chuyển user giữa tenants

Người dùng có thể được chuyển Acme → Beta theo một quy trình nhân sự. Đừng chỉ sửa path hoặc đổi email domain để “migrate”. Cần approval, identity link mới, revoke membership cũ, session invalidation theo policy, dữ liệu tenant tách biệt và audit. Một SAML login mới ở Beta chưa tự động cấp access tới dữ liệu Acme trước đây.

## 13. Threat model và negative test matrix

| Case | Mô phỏng trong staging | Kết quả đúng |
| --- | --- | --- |
| Happy path Acme | Host Acme, path Acme, IdP Acme signed Response hợp lệ | Login thành công và chỉ có quyền đã cấp tại tenant Acme |
| Happy path Beta | Host Beta, path Beta, IdP Beta signed Response hợp lệ | Login thành công vào tenant Beta |
| Host/path mismatch | Host Acme, `/t/beta/login` | Deny/404, không gửi AuthnRequest Beta |
| Host chưa đăng ký | `attacker.portal.example.org/t/acme/login` | Deny |
| Tenant slug lạ | `/t/evil/login` | Deny, không fallback IdP |
| Trực tiếp gọi generator | Host Acme, `/saml2/authenticate/beta` | Deny |
| Direct generator query | Host Acme, `/saml2/authenticate?registrationId=beta` | Deny trong demo |
| Cross-host ACS | POST SAMLResponse Beta tới host Acme path Beta | Deny ở host gate |
| Cross-IdP signature | IdP Beta ký Response gửi ACS Acme | Signature/issuer mismatch, không authenticated |
| Issuer text giả | Response tự ký với Issuer Acme | Không trust key của attacker |
| Wrong Audience | Signed Assertion Acme nhưng Audience Beta | Deny ở OpenSAML validator |
| Wrong Destination | Response Acme đúng signer nhưng Destination Beta ACS | Deny |
| Wrong Recipient | Bearer SubjectConfirmation Recipient Beta ACS | Deny |
| InResponseTo sai | Response trỏ AuthnRequest của browser/tenant khác | Deny |
| AuthnRequest state mất | Cookie/session không gửi về callback | Fail correlation, không cho qua |
| IdP-initiated khi policy cấm | Unsolicited SAMLResponse | Từ chối theo policy |
| SAML Response replay | Gửi lại response đã dùng | Deny theo session/replay policy |
| Account email trùng | IdP A/B cùng email nhưng identity khác | Không auto-link, không grant chéo tenant |
| Registration đúng nhưng user bị khóa | SAML authenticated Acme, internal user disabled | 403/deny app access |
| Registration Acme gọi resource Beta | `GET /t/beta/reports` với Acme principal | 403 |
| Forwarded spoof | Client gửi `X-Forwarded-Host: acme.portal.example.org` qua ingress không đúng | Edge xóa header giả, backend không tự trust |
| Meta URL attack | `?metadataUrl=http://169.254.169.254/...` | Không tải, deny input |
| Open redirect | `?returnUrl=https://attacker.example` | Không redirect sang URL ngoài allowlist |
| Unknown but plausible hostname | `acme.portal.example.org.evil.test` | Deny exact hostname |
| Tenant route disabled | Map/config status INACTIVE | Deny |
| Signing cert rotated | IdP ký bằng cert chưa cập nhật | Fail và xử lý rotation, không disable checks |
| Backend node B không có session | Callback sang node B | Shared session/state hoặc fail an toàn |

**Test chữ ký/Issuer/Audience cho đúng mục tiêu:** Nếu sửa Audience sau khi IdP ký, chữ ký đã sai; việc login fail khi đó **không chứng minh** Audience validator chạy. Dùng IdP test ký một Assertion hợp lệ **cho SP B**, rồi thử trình ở SP A trong staging. Tương tự, để test Destination riêng, cho IdP test phát Response hợp lệ với wrong destination; đừng tự sửa signed XML rồi kết luận nguyên nhân.

### 13.1. Unit test, integration test và browser E2E

- **Pure Java unit test:** `TenantRouteDemo` xác nhận exact match và deny unknown; chưa test network Host trust hoặc SAML.
- **Spring MVC test:** giả lập canonical host, gọi `GET /t/acme/login` và `GET /t/beta/login`, assert 303 và Location; assert mismatch 404.
- **Spring Security filter test:** thử trực tiếp `/saml2/authenticate/beta` trên Acme host, query-only generator, và cross-host ACS. Đảm bảo HostRegistrationGate được chạy trước SAML filters.
- **IdP integration:** dùng hai IdP sandbox có metadata và signing cert khác nhau; thử AuthnRequest, SAMLResponse, `InResponseTo`, issuer/audience/recipient và session handling.
- **Browser E2E:** TLS/SNI, canonical host, redirect, SameSite cookie, proxy forwarded headers, login lại và multi-tab.
- **Multi-instance:** phân phối request repository/session, metadata caching, node clocks và key rotation nhất quán.
- **Authorization/service tests:** một account thuộc Acme cố đọc data Beta dù SAML Authentication thành công; DB query phải ràng tenant server-side.

**Không nên kiểm thử bằng cách** tắt signature validation hoặc dùng signing private key production trong lab. Đừng đưa SAML XML, NameID, session cookies hay private keys vào log không được bảo vệ.

## 14. Lỗi phổ biến và cách điều tra

| Triệu chứng | Lớp lỗi có thể nằm ở | Hướng điều tra |
| --- | --- | --- |
| `404 Unapproved tenant route` | Host/path allowlist | Host canonical, tenantSlug, active mapping |
| `404` tại `/saml2/authenticate/...` | Direct generator guard | Host–registration pair, không bypass bằng query |
| Redirect sang IdP sai | Route mapping hoặc IdP picker | Chỉ dùng approved registration |
| ACS sai domain/port | Proxy/public URL hoặc IdP registration | SP metadata, fixed ACS, trusted forwarded headers |
| `Invalid Issuer` | IdP entity ID/trust | Response Issuer so với asserting party của registration |
| `Invalid Signature` | Cert mismatch/rotation | IdP public verification cert; không tin KeyInfo tự công bố |
| `Invalid Audience` | SP entity ID sai | AudienceRestriction trong Assertion và SP metadata |
| `Invalid Destination` | IdP gửi sai ACS | Expected ACS, host, scheme, path, binding |
| `Invalid Recipient` | Bearer confirmation sai | SubjectConfirmationData Recipient |
| `InResponseTo mismatch` | Request repository/session | Callback cookie, cluster, request ID và RelayState |
| User login thành công nhưng 403 tenant | Post-auth authorization đúng từ chối hoặc mapping thiếu | Identity link, membership và route tenant |
| User từ IdP A vào tenant B | Chưa kiểm registration sau login | Enforce principal registration/tenant policy |
| Two IdPs same Issuer | Lookup issuer mơ hồ | Use request state/path và approved registration |
| Lỗi chỉ trên một server | Configuration/session/cache khác nhau | Compare metadata, key, NTP, releases |
| Metadata không load | IdP URI unreachable/SSRF policy/cert error | Kiểm approved source, TLS, egress |
| Redirect sau login đi external URL | returnUrl/RelayState xử lý thiếu allowlist | Redirect policy, saved request và frontend |
| Một tenant alias bị login loop | Cookie scope/canonical host mismatch | Redirect canonical trước AuthnRequest, kiểm session cookie |

**Thứ tự điều tra hữu ích:** canonical Host → pathTenant → active route → registrationId → IdP metadata/trust → AuthnRequest state → signed SAML Response → Issuer/Audience/Destination/Recipient/InResponseTo → principal registration → internal identity link → resource authorization. Không sửa lỗi ở tầng sau bằng cách tắt validation tầng trước.

## 15. Checklist triển khai production

- [ ] Ingress chỉ chấp nhận domain đã triển khai, TLS/SNI phù hợp; backend không public trực tiếp.
- [ ] Forwarded headers được strip/rewrite tại trusted proxy, app không tin raw header từ client.
- [ ] Domain alias, tenant slug và registrationId được định nghĩa trong bảng quản trị có approval.
- [ ] Mọi unknown host/path/registration mặc định DENY, không chọn fallback IdP.
- [ ] Direct `/saml2/authenticate/{registrationId}` và query form không được bỏ qua tenant policy.
- [ ] ACS routes tương ứng registration, SP entity ID và public URL chính xác.
- [ ] IdP entity ID và verification cert đến từ approved metadata, không do SAMLResponse/URL parameter tự cấp.
- [ ] SAML provider giữ signature, issuer, audience, destination, recipient, time, subject confirmation và correlation checks.
- [ ] Session/request repository hỗ trợ callback qua load balancer và clock skew giới hạn.
- [ ] Unknown/multi-issuer situations có chính sách rõ; cấm IdP-initiated nếu không cần.
- [ ] After login: kiểm trusted registration, IdentityLink, tenant membership, user status, authorities và resource ownership.
- [ ] Không auto-link user qua email đơn lẻ, không coi tenant path là security principal.
- [ ] Secrets SP signing/decryption chỉ được workload có quyền đọc đúng environment/tenant.
- [ ] Domain/tenant onboarding, metadata refresh và cert rotation có approval, audit và rollback.
- [ ] Test negative cross-tenant, spoofed Host, malicious metadata URL, callback swap và open redirect.
- [ ] Logs chỉ ghi registrationId, tenantSlug đã sanitize, error category, correlation ID; không log raw SAMLResponse, NameID, credentials.
- [ ] Khả năng xử lý tenant aliases, shared host sessions, SLO và logout scope được đánh giá riêng.

## 16. Bài tập thực hành

**Bài A – nhận diện sáu loại ID.** Với mapping Acme ở mục 2, hãy liệt kê host, path tenant, registrationId, IdP entity ID, SP entity ID và ACS. Giải thích vì sao một URI metadata và một Issuer không nhất thiết trùng nhau.

**Bài B – Java 17.** Chạy `TenantRouteDemo.java`, xác nhận sáu dòng stdout. Thêm test `("beta.portal.example.org","acme")` và chứng minh kết quả `DENY`. Thêm alias chỉ sau khi có yêu cầu duyệt thay đổi route.

**Bài C – direct endpoint bypass.** Không dùng `/t/acme/login` mà gọi thẳng `/saml2/authenticate/beta` trên hostname Acme. Dựa theo filter mục 9, nêu lý do 404. Sau đó giải thích vì sao dù filter chạy, OpenSAML vẫn cần xác minh Response.

**Bài D – IdP test.** Đăng ký hai cặp SP/IdP trong sandbox. Thực hiện login Acme và Beta riêng, đối chiếu AuthnRequest Issuer/ACS, Response Issuer, Audience và Result registrationId. Không sử dụng IdP private key trong SP.

**Bài E – cross-tenant authorization.** Giả lập user đã login qua Acme; thử truy cập resource Beta. Giải thích tại sao chỉ check `authenticated()` không đủ; thiết kế service kiểm tenant membership và resource ownership.

**Bài F – shared host.** Thiết kế `portal.example.org/t/acme/login` và `portal.example.org/t/beta/login`. Xác định ít nhất hai vấn đề: một browser cookie/session có thể không đại diện hai tenant đồng thời và ACS cần phân biệt registrations. Đề xuất policy session/URL cụ thể.

**Bài G – custom domain.** Acme muốn dùng `login.acme-company.example`. Vẽ bước xác minh domain ownership, TLS, canonical-host redirect, mapping approval và thay đổi IdP ACS. Giải thích tại sao không thể thêm alias tùy ý mà không đánh giá cookie/correlation.

**Bài H – threat model.** Nêu ba trường hợp có thể phát sinh SSRF/open redirect khi ứng dụng dùng `?tenant` hoặc `?metadataUrl` và cách allowlisted repository loại bỏ đường tấn công.

**Bài I – IdP cùng issuer.** Hai tenants trỏ về cùng một IdP entity ID. Trình bày tại sao `Response/Issuer` không đủ để chọn tenant, và vai trò của registrationId trong AuthnRequest state, Audience và post-auth membership.

**Tiêu chí đạt:** Người học chỉ được chính xác ba ranh giới **(host,path) allowlist trước login → SAML signature/issuer/audience/ACS/correlation validation trong login → tenant authorization sau login**; tạo được two-tenant app mẫu và nêu ít nhất năm negative tests quan trọng.

## 17. Tài liệu chính thức

- Spring Security 6.5 – SAML 2.0 Login Overview, `RelyingPartyRegistrationRepository` và URI patterns: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security 6.5 – Authenticating SAML Responses, customizing registration lookup: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html
- Spring Security 6.5 – Producing AuthnRequests, request URI và repository: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication-requests.html
- Spring Security 6.5 API – `Saml2AuthenticationTokenConverter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationTokenConverter.html
- Spring Security 6.5 API – `Saml2AuthenticatedPrincipal`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html
- Spring Security – SAML2 SP metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.5 – SAML Relying Party and OpenSAML dependencies: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS SAML 2.0 Core, Issuer, Audience và SubjectConfirmation: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles, Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML 2.0 Metadata, EntityDescriptor/ACS: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
