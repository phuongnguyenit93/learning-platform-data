# Chẩn đoán mất AuthnRequest, sai InResponseTo và cookie không được gửi

## 1. Mục tiêu và bối cảnh lỗi

Trong **Spring Security - federation**, nhóm **Quan sát và gỡ lỗi**, một tình huống thường gặp của SAML 2.0 Web SSO là người dùng đăng nhập và hoàn tất MFA tại Identity Provider (IdP), browser nhận trang POST SAMLResponse về ứng dụng, nhưng Spring Security không lập được phiên, trả 401/403 hoặc chuyển người dùng trở lại màn hình đăng nhập.

Không nên gộp mọi lỗi thành một nhãn “SAML không thành công”. Có ba hiện tượng quan trọng cần phân biệt:

1. **Mất AuthnRequest**: SP đã tạo yêu cầu đăng nhập, nhưng ở callback không đọc lại được yêu cầu đã lưu.
2. **InResponseTo không khớp**: IdP trả về Response tham chiếu AuthnRequest A, còn SP đang kiểm tra request B hoặc không có request nào.
3. **Cookie không được gửi hoặc session không có**: browser không gửi cookie phiên SP qua POST cross-site, hoặc cookie vẫn có nhưng server không tìm được dữ liệu phiên.

Các nguyên nhân có thể là SameSite, Secure/Domain/Path, session timeout, reverse proxy, load balancer, Spring Session, request repository, concurrent tabs, callback route sai và IdP-initiated SSO. Chúng có triệu chứng tương tự nhưng cách xử lý khác hẳn.

**Mục tiêu học tập:** hiểu chuỗi SAML request/response và state, chẩn đoán theo chứng cứ từ browser đến IdP/Spring/server session, phân loại lỗi InResponseTo, bảo vệ login CSRF và chống replay, thiết kế log không rò rỉ assertion/cookie, có Java 17 chạy độc lập, ma trận negative tests và checklist nghiệm thu.

> **Bất biến bảo mật:** Đối với **SP-initiated SSO**, AuthnRequest đã phát và SAMLResponse nhận về phải khớp đúng giao dịch/browser binding theo policy. Không bỏ kiểm tra InResponseTo, RelayState, chữ ký, issuer, audience hay recipient chỉ để người dùng đăng nhập lại thành công.

## 2. Năm tên gần giống nhau nhưng không thay thế nhau

| Dữ liệu | Nguồn | Vai trò | Nhầm lẫn phải tránh |
| --- | --- | --- | --- |
| **AuthnRequest ID** | SP tự sinh trong XML `<saml2:AuthnRequest ID="_REQ-A">` | Định danh một yêu cầu xác thực đã phát. | Không phải SAMLResponse ID hay session ID. |
| **Response InResponseTo** | IdP trả trong `<saml2:Response>` và/hoặc SubjectConfirmationData | Khai báo Response đang trả lời AuthnRequest nào. | Không đủ chứng minh browser hiện tại đã khởi tạo request. |
| **RelayState** | SP gửi kèm AuthnRequest, IdP chuyển lại theo binding | Opaque correlation / trạng thái ứng dụng. | Không phải chữ ký SAML, không là URL redirect đáng tin mặc định. |
| **JSESSIONID / HttpSession** | Server SP cấp session, browser lưu cookie | Gắn browser với pending AuthnRequest trong session repository mặc định. | Không phải AuthnRequest ID, cũng không tự thay chứng cứ SAML. |
| **RelyingPartyRegistrationId** | Config của Spring Security | Chọn IdP, ACS, verification credentials và SP entityID. | Không là IdP issuer hoặc bằng chứng caller đã được xác thực. |

**Response ID** và **Assertion ID** là hai ID khác dùng cho chống phát lại và tracing của bản tin. **IdP entityID**, **SP entityID**, **Destination**, **Recipient**, **AudienceRestriction** cũng là các trường khác. Khi so sai loại ID, rất dễ kết luận nhầm “InResponseTo lỗi”.

### 2.1. Một lần đăng nhập tương quan đúng

```text
SP creates:
  sessionRef    : S1
  registration  : corp-idp
  request ID    : _REQ-A1
  RelayState    : R-A1
  expected ACS  : https://portal.example.org/login/saml2/sso/corp-idp

IdP receives AuthnRequest ID=_REQ-A1 and RelayState=R-A1.

Browser returns:
  POST /login/saml2/sso/corp-idp
  SAMLResponse:
    Response ID=_RESP-B1
    InResponseTo=_REQ-A1
    Issuer=https://idp.corp.example/saml
    Destination=https://portal.example.org/login/saml2/sso/corp-idp
  RelayState=R-A1
  Cookie: JSESSIONID=<redacted>

SP repository finds pending request _REQ-A1,
bound to the expected browser transaction.
  -> correlation MATCH
  -> validate XML signature, issuer, audience, recipient,
     Conditions, SubjectConfirmation and replay
  -> create Authentication only after all checks
```

**Khớp InResponseTo chưa phải login thành công.** Kẻ tấn công không được nâng quyền nếu signed assertion sai issuer/audience, đã hết hạn hoặc local user bị vô hiệu hóa.

## 3. Spring Security SAML2 Web SSO: chuỗi filter và repository

Theo Spring Security Servlet, luồng SP-initiated:

```text
Browser         Spring Security SP                 IdP
  |                    |                            |
  | GET /reports       |                            |
  |------------------->|                            |
  |<-------------------| 302 /saml2/authenticate/corp
  |                    |                            |
  | GET /saml2/authenticate/corp                      |
  |------------------->|                            |
  |                    | Saml2WebSsoAuthenticationRequestFilter
  |                    | create AuthnRequest _REQ-A
  |                    | save via Saml2AuthenticationRequestRepository
  |                    | redirect with SAMLRequest, RelayState
  |<-------------------|                            |
  | Redirect to IdP -------------------------------->|
  |                    |                            | user MFA
  | Browser POST ACS  |<----------------------------|
  |------------------->|                            |
  |                    | Saml2WebSsoAuthenticationFilter
  |                    | Saml2AuthenticationTokenConverter
  |                    | load pending AuthnRequest
  |                    | validate response with OpenSAML provider
  |                    |                            |
  | success / failure  |                            |
  |<-------------------|                            |
```

Các endpoint phổ biến:
- **Tạo AuthnRequest**: `/saml2/authenticate/{registrationId}`.
- **Nhận SAMLResponse tại ACS**: `/login/saml2/sso/{registrationId}`.

Trong Spring Security hiện hành, `Saml2WebSsoAuthenticationRequestFilter` dùng **`Saml2AuthenticationRequestRepository`** để lưu một `AbstractSaml2AuthenticationRequest` trước khi chuyển browser sang IdP; `Saml2WebSsoAuthenticationFilter` và `Saml2AuthenticationTokenConverter` có thể dùng repository để lấy lại request.

**Mặc định là `HttpSessionSaml2AuthenticationRequestRepository`**, lưu pending request trong `HttpSession`. Cơ chế này phụ thuộc sự ràng buộc browser↔session xuyên suốt quá trình ra IdP rồi quay lại.

**Lưu ý version:** Spring Security 6.x/7.x và custom repository có thể có API/defaults khác nhau. Luôn ghi exact dependency version, filter chain đang chạy, repository implementation, loại session store và binding (HTTP-POST/Redirect) trước khi kết luận.

## 4. Phân biệt ba lỗi cốt lõi bằng chứng cứ

### 4.1. AuthnRequest không được tìm thấy

```text
T0: save AuthnRequest A in browser session S1.
T1: callback POST from IdP contains InResponseTo=A.
T2: loadAuthnRequest(callback) returns null.
```

Các khả năng:
- Browser **không gửi JSESSIONID** do SameSite/scope/browser policy.
- Browser gửi cookie nhưng gateway/WAF không forward.
- Session S1 đã timeout, invalidate hoặc evict.
- Callback đến một app node không chia sẻ session với node tạo request.
- Repository lưu vào session nhưng callback load từ cache repository khác.
- Request bị consume/remove trước, duplicate ACS callback hoặc filter chạy hai lần.
- App restart/rolling deploy gây mất in-memory session hoặc serialization fail.
- Nhiều tab ghi đè một request trong session, rồi request bị xóa.
- ACS được route sang staging/host khác.

**Chỉ một log “request not found” không đủ suy rằng IdP đã trả sai InResponseTo.**

### 4.2. Có request nhưng sai InResponseTo

```text
AuthnRequest saved or loaded : _REQ-B
SAMLResponse.InResponseTo    : _REQ-A

=> MISMATCH, dù SAMLResponse có chữ ký hợp lệ.
```

Đây có thể là **concurrency**: tab A gửi request A, tab B cùng HTTP session gửi request B; cách lưu chỉ giữ một request sẽ ghi đè A. Những khả năng khác: IdP response cho request cũ, RelayState sai, registration khác, session bất ngờ đổi hoặc cache mapping trộn giao dịch.

### 4.3. Cookie vắng mặt ở tầng nào?

| Tầng | Triệu chứng | Phân tích đúng |
| --- | --- | --- |
| HTTP response SP | Không thấy Set-Cookie | Có thể đã có cookie cũ; cần xem Application/Storage. |
| Browser nhận Set-Cookie | Browser từ chối lưu | SameSite=None thiếu Secure, Domain hoặc browser policy. |
| Browser gửi ACS | Cookie excluded | SameSite, Secure, Domain, Path, iframe/third-party policy. |
| Reverse proxy | Browser included nhưng app thiếu Cookie | Ingress/WAF/CDN strip hoặc rewrite. |
| Spring Servlet | Cookie có nhưng `getSession(false)` null | Session expired/evicted/namespace/node mismatch. |
| Repository | Session hiện hữu nhưng request null | Save failed, remove, overwrite hoặc repo contract mismatch. |

Đừng gọi cả sáu hiện tượng là “cookie bị mất”. Mỗi tầng có cách khắc phục và kiểm thử riêng.

## 5. SameSite và SAML HTTP-POST: nguyên nhân xuất hiện thường xuyên

Trong HTTP-POST Binding, IdP render HTML form để **browser POST từ IdP site sang ACS của SP**. Nếu hai hệ thống khác site, đây là **cross-site POST không phải safe method**.

| Cookie attribute | Cross-site top-level GET | Cross-site top-level POST | Tác động |
| --- | --- | --- | --- |
| `SameSite=Strict` | Không gửi | Không gửi | Ngay cả return navigation GET từ IdP cũng có thể mất session. |
| `SameSite=Lax` (explicit) | Thường gửi | Thường **không gửi** | SAMLResponse POST dễ không mang JSESSIONID. |
| `SameSite=None; Secure` | Có thể gửi | Có thể gửi | Cần HTTPS; vẫn bị giới hạn bởi browser privacy/partition policy. |
| Không set SameSite | Browser chọn default (thường Lax) | Có thể có browser-specific grace window | Không đủ ổn định để thiết kế SSO. |

MDN lưu ý một số browser áp dụng **default Lax** có chế độ nới lỏng cho POST khi cookie mới tạo khoảng **hai phút**. Điều này có thể khiến login nhanh thành công, nhưng người dùng mất nhiều phút làm MFA thì fail. **Không nhầm ngoại lệ default-Lax với `SameSite=Lax` tường minh**, cũng không dựa vào grace period để vận hành.

### 5.1. Dấu vết HTTP minh họa

```http
HTTP/1.1 302 Found
Location: https://idp.corp.example/sso?SAMLRequest=...&RelayState=...
Set-Cookie: JSESSIONID=<redacted>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Khi callback:

```http
POST /login/saml2/sso/corp-idp HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded
Origin: https://idp.corp.example

SAMLResponse=<redacted>&RelayState=<redacted>
```

Browser có thể **không gửi Cookie: JSESSIONID** trên POST này. Spring không tìm được HTTP session chứa AuthnRequest A. Các header ví dụ chỉ mô tả dữ liệu thường gặp; Origin/Fetch Metadata có thể vắng hoặc khác theo browser. **Origin không thay thế validation chữ ký SAML.**

### 5.2. Spring Boot cookie config: chỉ áp dụng sau khi xác minh nguyên nhân

Ví dụ properties:

```properties
server.servlet.session.cookie.same-site=none
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
```

Tài liệu Spring Boot hỗ trợ `server.servlet.session.cookie.same-site` cho các container được tích hợp và servlet Spring Session repository theo phiên bản. **Không coi config này là thuốc chữa mọi lỗi SAML.** Kiểm tra cookie writer, ứng dụng đang dùng Boot/container nào, public HTTPS và ACS path.

Với `SameSite=None`, browser có thể gửi session cookie trên những cross-site requests rộng hơn; **mọi thao tác nghiệp vụ dùng cookie vẫn cần bảo vệ CSRF**, chẳng hạn CSRF token/Origin/Fetch Metadata policy phù hợp. ACS SAML POST có thể cần một **CSRF exemption hẹp đúng callback matcher**, nhưng không tắt CSRF toàn app hoặc admin endpoints.

### 5.3. Khi None không giải quyết

- Cookie `Path=/app` nhưng callback ACS là `/login/saml2/sso/...` (ngoài Path).
- Cookie host-only thuộc `old.portal.example.org`, còn IdP POST sang `portal.example.org`.
- Cookie Secure nhưng callback dùng HTTP do public ACS sai.
- Browser/iframe ngăn third-party cookies bất kể SameSite=None.
- Browser đã xóa cookie hoặc user mở private browsing context.
- Proxy/WAF strip Cookie hoặc rewrite Domain.
- Session store expire trong lúc MFA.
- Callback vào node không có session.
- Multi-tab overwrite dù JSESSIONID được gửi.

**Không dùng thay đổi SameSite để che lỗi InResponseTo do hai tab.**

## 6. Điều tra bằng Browser DevTools / Network

Chỉ thực hiện với **test accounts** và dữ liệu không nhạy cảm; bật Preserve log:

1. Bắt đầu truy cập một protected resource ở SP.
2. Tìm request `GET /saml2/authenticate/{registrationId}` và outbound `SAMLRequest`.
3. Kiểm tra response `Set-Cookie` theo **attributes**: name, Path, Domain, Secure, HttpOnly, SameSite, Max-Age; **không sao chép giá trị cookie**.
4. Ghi browser/version, normal tab hay iframe, HTTP method và cross-site context.
5. Theo luồng IdP/MFA đến ACS `POST /login/saml2/sso/...`.
6. Mở tab Cookies của ACS request, tìm **Included/Excluded** và **lý do cụ thể**.
7. Kiểm tra public ACS origin, host, path, scheme và `Set-Cookie` scope.
8. Chỉ ghi boolean có/không của `SAMLResponse` và `RelayState`, không export raw XML/Base64 assertions.
9. Ghép với application trace qua correlation ID riêng.
10. Lặp lại có kiểm soát: 1 tab, 2 tab, MFA nhanh/chậm, clean browser, browser khác.

**HAR export có thể chứa cookies, SAMLResponse, NameID và PII.** Nếu cần dùng HAR, phải redact ở nơi được bảo vệ, giới hạn quyền đọc và thời gian giữ. Không đưa raw HAR hoặc bearer assertion lên issue tracker công khai.

### 6.1. Browser evidence → bước debug

| Browser Network thấy | Ưu tiên kiểm |
| --- | --- |
| Cookie excluded vì SameSite | Cross-site POST vs GET, Lax/Strict/None. |
| Cookie excluded vì Secure | HTTPS public callback và reverse proxy. |
| Cookie excluded vì Domain/Path | Scope cookie so với ACS. |
| Cookie included nhưng app không thấy | Proxy forwarding/filter/WAF. |
| Cookie included, session found, loaded request B | Multi-tab/repository overwrite. |
| Không có outbound SAMLRequest | Initiation flow hoặc IdP-initiated SSO. |
| ACS POST blocked 403 trước SAML filter | CSRF matcher/WAF/chain order. |
| Request found, InResponseTo match nhưng signature fail | IdP cert/trust; không phải cookie. |

## 7. Instrumenting repository để biết request đã thực sự được lưu

`HttpSessionSaml2AuthenticationRequestRepository` dùng HttpSession làm nơi lưu pending request. Để chẩn đoán phải ghi **event từ thao tác save/load/remove thật**, không tự gọi repository thêm lần nữa.

Ví dụ schema instrumentation:

```text
event=SAML_AUTHN_REQUEST_CREATED
trace=login-001
registration=corp-idp
request_ref=HMAC(_REQ-A)
relay_ref=HMAC(R-A)
session_ref=HMAC(S1)
node=portal-1

event=SAML_AUTHN_REQUEST_SAVED
trace=login-001
repository=HttpSession
outcome=SUCCESS
request_ref=HMAC(_REQ-A)
session_ref=HMAC(S1)
node=portal-1

event=SAML_RESPONSE_RECEIVED
trace=acs-319
method=POST
session_cookie_present=true
server_session_found=true
response_in_response_to_ref=HMAC(_REQ-A)
node=portal-2

event=SAML_AUTHN_REQUEST_LOADED
trace=acs-319
repository=HttpSession
outcome=FOUND
stored_request_ref=HMAC(_REQ-A)
node=portal-2

event=SAML_CORRELATION
trace=acs-319
decision=MATCH
```

Đây là **schema đề xuất**, không phải log Spring Security mặc định. Dùng **HMAC keyed references** cho dữ liệu nhạy cảm, không ghi raw SAMLResponse, RelayState, session IDs hoặc AttributeStatement. Các labels `node`, `registration`, `repository`, `outcome` có ích cho multi-node so sánh.

### 7.1. Những kết quả cần phân biệt

| Save | Cookie/session khi ACS | Load | Kết luận tạm thời |
| --- | --- | --- | --- |
| A saved vào S1 | Không có S1 | NOT_FOUND | Browser Cookie/ingress. |
| A saved vào S1 | Cookie S1 có, session absent | NOT_FOUND | Session TTL/eviction/node. |
| A saved vào S1 | Session S1 có, attribute absent | NOT_FOUND | Remove/overwrite/replication/repo mismatch. |
| A rồi B saved trong S1 | Session S1 có, load B, response A | MISMATCH | Multi-tab overwrite hoặc wrong mapping. |
| A saved và load A | Response InResponseTo=A | MATCH | Nếu vẫn fail, kiểm validation khác. |

**Điều tra session mất phải dùng `request.getSession(false)`**. `request.getSession()` có thể tạo session mới, khiến log “server session present” không còn ý nghĩa đối với session đã lưu AuthnRequest.

### 7.2. Lỗi do chính instrumentation

- Một filter debug gọi `removeAuthnRequest` để “xem state”, rồi filter SAML gọi lại và không tìm thấy.
- Custom filter được đăng ký hai lần, khiến request bị load/remove hai lần.
- Một callback bị browser retry/replay, lần đầu đã consume request.
- Wrapper tính correlation theo cookie hiện tại nhưng session đã rotate trước callback.
- Filter debug vô ý in raw query chứa SAMLRequest/RelayState.

**Không tạo side effects khi quan sát.** Chỉ bọc lời gọi do framework thực hiện, redact bí mật và test duplicate callbacks.

## 8. Hai tab cùng HttpSession: sai InResponseTo dù cookie vẫn có

Một browser có hai tabs cùng `JSESSIONID=S1`:

```text
T0 Tab A:
  AuthnRequest ID=_REQ-A
  RelayState=R-A
  session[SAML_REQUEST] = _REQ-A

T1 Tab B:
  AuthnRequest ID=_REQ-B
  RelayState=R-B
  session[SAML_REQUEST] = _REQ-B

T2 Tab A finishes IdP login first:
  POST ACS with JSESSIONID=S1
  SAMLResponse InResponseTo=_REQ-A

Repository:
  load session[SAML_REQUEST] = _REQ-B

=> _REQ-A != _REQ-B -> failure.
```

Spring Security đã có báo cáo issue #14793 về cách lưu request bằng một session key khiến yêu cầu mới ghi đè yêu cầu cũ trong một số versions. **Không kết luận mọi phiên bản giống nhau**; phải quan sát class/release thực tế và các sự kiện save A, save B, load A/B.

### 8.1. Bằng chứng xác nhận

1. Một tab riêng login thành công.
2. Bật safe requestRef/sessionRef logging.
3. Mở tab A, start SSO; trước callback mở tab B, start SSO.
4. Ghi `SAVE A`, `SAVE B` và cùng sessionRef.
5. Cho callback tab A về, ghi `LOAD B`, `InResponseTo A` và mismatch.
6. Đảo thứ tự callback để tái hiện có hệ thống.
7. Lặp lại nhiều nodes, nếu có.
8. Sau thay đổi repository, cả hai tabs phải có kết quả đúng và replay bị từ chối.

**Không bỏ InResponseTo validation** chỉ vì single-tab success/multi-tab failure. Cần một thiết kế có khả năng lưu nhiều pending AuthnRequests riêng biệt.

## 9. CacheSaml2AuthenticationRequestRepository và đánh đổi browser-binding

Trong các phiên bản mới, Spring Security có `CacheSaml2AuthenticationRequestRepository`, có thể cache AuthnRequest theo RelayState. Nó hữu ích khi HTTP session không phù hợp với strict cookie rules, hoặc cần nhiều request cùng chờ.

Một record giao dịch nên gồm:

```text
key:
  unpredictable one-time RelayState reference

value:
  AuthnRequest ID
  relying-party registration
  expected IdP entityID
  expected ACS and SP entityID
  issuedAt, expiresAt
  original browser/session transaction binding
  safe post-login relative destination
  state=PENDING
```

Khi callback:
1. Lookup record bằng opaque transaction key.
2. Kiểm tra browser/session binding hoặc một cơ chế chống login CSRF tương đương.
3. Đối chiếu `InResponseTo` với AuthnRequest ID.
4. Xác minh signature, issuer, audience, recipient/destination, Conditions, SubjectConfirmation và replay.
5. One-time atomic consume/cleanup; không dùng lại record sau login.
6. Hết TTL/không có record/conflict → deny, không fallback auto-login.

### 9.1. Cảnh báo chính thức của Spring Security

Session-based repository có lợi thế tự nhiên chống **login fixation**: response từ attacker không tìm thấy AuthnRequest trong session browser của nạn nhân. Nếu chỉ dùng `RelayState` hoặc `InResponseTo` của inbound response để tìm AuthnRequest trong **cache chung**, **không có gì tự chứng minh browser nạn nhân đã khởi tạo giao dịch đó**.

Do đó:
- Không coi “đưa request vào Redis keyed by RelayState” tự là fix an toàn.
- Thêm binding giữa request và browser gốc hoặc kiểm soát login CSRF tương đương, có review.
- RelayState phải khó đoán, TTL ngắn và one-time, không chứa session secrets.
- Không dùng RelayState làm URL redirect tùy ý.
- So đủ IdP/registration/tenant, không chỉ ID.
- Test cross-browser response injection, replay và callback retry.
- Không tắt session fixation strategy để sửa SSO.

### 9.2. Per-session map cũng không miễn rủi ro

Nếu dùng `Map<RelayState, PendingRequest>` trong HttpSession:
- Map mutable cần concurrency control khi nhiều threads.
- Spring Session/serialization có thể không persist in-place mutations như developer tưởng.
- Lost updates có thể xảy ra khi hai nodes cùng sửa snapshot session.
- Phải re-set session attribute hoặc dùng atomic distributed store theo contract.
- Dùng quotas/TTL và dọn đúng transaction, không xóa toàn bộ tabs.
- Cân nhắc rolling deployment/class changes, store errors và fail closed.

## 10. Reverse proxy, forwarded headers và ACS URL

Ví dụ:

```text
Public browser origin:
  https://portal.example.org

Internal Spring app:
  http://portal-service:8080

Configured ACS at IdP:
  https://portal.example.org/login/saml2/sso/corp-idp
```

Nếu Spring hoặc IdP nhầm một URL nội bộ, cookie có thể được set vào host khác, request callback route sai và SAML Recipient/Destination cũng có thể mismatched.

| Kiểm tra | Từ đâu lấy? | So với |
| --- | --- | --- |
| Public ACS URL | Browser Network | IdP registration/metadata. |
| AuthnRequest AssertionConsumerServiceURL | Outbound SAMLRequest (parse có kiểm soát) | Public ACS. |
| Response Destination | Validated response context | Expected ACS. |
| SubjectConfirmationData Recipient | Assertion | Expected service/ACS. |
| Registration ID | Spring path/metadata | Allowed IdP entityID. |
| Cookie Domain/Path/Secure | Browser cookie view | Public ACS origin/path. |
| Forwarded-Host/Proto | Approved ingress | External HTTPS host; không tin attacker headers. |
| Backend node/store namespace | App trace | Request creation node/store. |

Spring Boot property:

```properties
server.forward-headers-strategy=framework
```

có thể hữu ích nếu kiến trúc có **trusted reverse proxy**. Nhưng chỉ bật khi ingress **loại bỏ user-supplied X-Forwarded-Host/Proto/Port** và ghi giá trị thật; nếu không attacker có thể khiến app dựng ACS/redirect sai. Cần test exact public URLs, không mở wildcard ACS/redirect vì cấu hình chưa khớp.

### 10.1. Cookie Path/Domain/Name

- Cookie `Path=/app` không được gửi tới ACS `/login/saml2/sso/corp-idp`.
- Cookie host-only cho `old.portal.example.org` không đi sang `portal.example.org`.
- Cookie Secure sẽ không đi theo HTTP callback trên public Internet.
- Có thể có nhiều cookies cùng tên JSESSIONID ở các Path/Domain khác nhau; server chọn nhầm.
- Ingress rewrite Set-Cookie hoặc Cookie có thể làm thay cookie policy.
- HSTS, TLS termination và port/context path phải nhất quán.

**Chỉ cấp Domain rộng khi thật sự cần.** Host-only cookie với Path tối thiểu đủ dùng giảm phạm vi dữ liệu session có thể lộ.

## 11. Multi-node session store và session fixation

Ví dụ:

```text
GET initiation:
  Node A creates S1 and saves AuthnRequest _REQ-A
Callback:
  Node B receives JSESSIONID=S1
  Node B only has local in-memory HttpSession
  -> session not found
```

Sticky sessions có thể giảm xác suất, nhưng không giải quyết restart, node failure, LB rebalance, rolling deploy. Spring Session Redis/JDBC hoặc một distributed request store phù hợp hơn khi cần multi-node consistency.

**Cần kiểm:**
- Node A/B dùng cùng session namespace/prefix/config?
- Session TTL vượt thời gian MFA thực tế?
- Session attribute AuthnRequest đã serialize và persist?
- Store có eviction, timeouts hoặc lỗi deserialize sau rollout?
- Callback duplicate đã remove request trước?
- Repo save/load có cùng implementation và config?
- Session ID có thay trước callback do logout/invalidations?

### 11.1. Đổi session ID trước và sau authentication

```text
Normal:
 T0 create and save AuthnRequest in S1
 T1 callback uses S1, request loads and matches
 T2 SAML authentication succeeds
 T3 session-fixation strategy may rotate ID

Problem:
 T0 save pending request in S1
 T1 logout/Session invalidation or S2 created too early
 T2 callback cannot find original pending request
```

**Session ID được rotate sau authentication success có thể hoàn toàn đúng.** Không tắt session fixation protection. Muốn tìm root cause, timestamp từng bước và phân biệt sự kiện trước/sau callback.

## 12. IdP-initiated SSO: không có AuthnRequest từ đầu

Khi user click tile tại dashboard IdP, IdP có thể gửi response **unsolicited**, không có SP AuthnRequest và có thể không có InResponseTo. Đây là profile **IdP-initiated**, khác SP-initiated.

- Nếu app policy chỉ cho SP-initiated, unsolicited SAMLResponse **phải reject**.
- Nếu business yêu cầu IdP-initiated, cần policy được phê duyệt với trusted issuer, signature, audience, recipient, replay, user/tenant authorization và giải pháp chống login CSRF/session confusion.
- Không tự chuyển một lỗi `AuthnRequest not found` thành `accept unsolicited` để đăng nhập được.
- Audit nên phân biệt SP-initiated với IdP-initiated để chẩn đoán chính xác.

**Không có AuthnRequest** và **mất AuthnRequest đã từng có** là hai trường hợp khác về bảo mật và vận hành.

## 13. Phân biệt lỗi correlation với lỗi SAML validation khác

| Trạng thái | Nhóm lỗi |
| --- | --- |
| Repository load null | Cookie/session/repo/overwrite/timeout. |
| Loaded ID B nhưng Response InResponseTo A | Transaction mapping hoặc concurrent tabs. |
| RelayState inbound không khớp outbound | IdP/state propagation/encoding/repository. |
| Response signature invalid | IdP signing cert/metadata/XML signature. |
| Wrong issuer | Đối tác/registration không đúng. |
| Wrong audience | Assertion dành SP khác. |
| Wrong Destination/Recipient | ACS reverse proxy/metadata sai. |
| NotBefore/NotOnOrAfter invalid | Clock skew/NTP/assertion expired. |
| SubjectConfirmation failure | Điều kiện bearer/recipient/correlation không đúng. |
| Assertion replay | Duplicate SAMLResponse / replay store. |
| CSRF/WAF 403 trước SAML filter | HTTP routing/security chain, chưa tới XML validation. |
| Local account disabled sau SAML verify | Application admission, không phải cookie. |
| Resource permission denied | Authorization, không phải federation authentication. |

**Tương quan đúng không bỏ được validation mật mã**, và validation mật mã đúng không tự chứng minh correlation/SP-initiated flow.

## 14. Instrumentation Spring Security không tiết lộ cookie

**Không sử dụng**:

```java
log.info("Cookie={}", request.getHeader("Cookie"));
log.info("SAMLResponse={}", request.getParameter("SAMLResponse"));
log.info("Session={}", request.getSession().getId());
```

Đây vừa rò bearer material/PII, vừa có nguy cơ **tạo session mới khi gọi getSession()**.

### 14.1. Filter minh họa quan sát presence

Mảnh mã sau dành cho **dự án Spring Boot Servlet/Jakarta với SLF4J**, không phải Java SE độc lập. Phải đăng ký filter đúng một lần, tránh đặt vừa Servlet Filter Bean vừa add vào SecurityFilterChain khiến chạy hai lần.

```java
package example.sso;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

public final class SamlCookieProbeFilter extends OncePerRequestFilter {
    private static final Logger LOG =
        LoggerFactory.getLogger(SamlCookieProbeFilter.class);

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return !path.contains("/saml2/authenticate/")
            && !path.contains("/login/saml2/sso/");
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain) throws ServletException, IOException {

        boolean hasSessionCookie = false;
        Cookie[] cookies = request.getCookies();
        if (cookies != null) {
            for (Cookie cookie : cookies) {
                if ("JSESSIONID".equals(cookie.getName())) {
                    hasSessionCookie = true;
                    break;
                }
            }
        }

        LOG.info("saml_probe path={} method={} cookie_present={} "
                + "session_found={} session_id_valid={}",
            request.getRequestURI(),
            request.getMethod(),
            hasSessionCookie,
            request.getSession(false) != null,
            request.isRequestedSessionIdValid());

        chain.doFilter(request, response);
    }
}
```

**Giới hạn:** log only booleans và route, không in cookie value hoặc SAML XML; phải đổi cookie name nếu tổ chức dùng tên khác. Để xác định request A/B cần wrapper repository ghi hashed request/RelayState refs. Không tự thêm calls `load/remove` để debug, vì có thể tiêu thụ state.

### 14.2. Pseudocode wrapper repository an toàn

```text
saveAuthnRequest(request):
    derive safe requestRef, relayRef, sessionRef using HMAC
    delegate.save(...)
    emit SAVED status + node + registration + repoType

loadAuthnRequest(callback):
    derive safe browser/callback presence flags
    delegate.load(...)
    emit FOUND / NOT_FOUND + storedRequestRef if found

removeAuthnRequest(callback):
    delegate.remove(...)
    emit REMOVED / ALREADY_ABSENT
```

Cấu trúc method/generic type thay đổi theo Spring Security version; đoạn trên **không phải Java API drop-in**. Mọi event cần loại bỏ raw SAML assertion, cookies, NameID, URL chứa RelayState.

## 15. Java 17 runnable: tái hiện cookie loss, InResponseTo mismatch và multi-request storage

Chương trình Java SE sau dùng **HashMap và record** để minh họa các quy tắc. Nó không kết nối IdP, không xác minh SAML XML, không có TLS, HTTP session hay multi-node store.

- `SinglePendingSessionRepository`: một request per session, tab B sẽ ghi đè tab A.
- `PerTransactionRepository`: lookup theo RelayState, nhưng còn kiểm browser-session binding, InResponseTo, TTL và one-time consume.
- `cookieSent`: mô hình giản lược SameSite **explicit**, không mô phỏng default-Lax grace, browser privacy, Domain/Path, iframe/partition.

Tệp **SamlCorrelationDiagnosticsDemo.java**:

```java
import java.util.HashMap;
import java.util.Map;

public final class SamlCorrelationDiagnosticsDemo {

    record Login(String id,
                 String relay,
                 String browserSession,
                 long expiresAt) {}

    static final class SinglePendingSessionRepository {
        private final Map<String, Login> pending = new HashMap<>();

        void save(Login request) {
            pending.put(request.browserSession(), request);
        }

        String callback(String browserSession, String inResponseTo) {
            if (browserSession == null) return "COOKIE_MISSING";
            Login found = pending.get(browserSession);
            if (found == null) return "REQUEST_NOT_FOUND";
            if (!found.id().equals(inResponseTo))
                return "IN_RESPONSE_TO_MISMATCH";
            return "MATCH";
        }
    }

    static final class PerTransactionRepository {
        private final Map<String, Login> pendingByRelay = new HashMap<>();

        void save(Login request) {
            pendingByRelay.put(request.relay(), request);
        }

        String callback(String relay, String inResponseTo,
                        String browserSession, long now) {
            if (relay == null) return "RELAY_MISSING";
            Login found = pendingByRelay.get(relay);
            if (found == null) return "REQUEST_NOT_FOUND";
            if (!found.browserSession().equals(browserSession))
                return "BROWSER_BINDING_MISMATCH";
            if (now >= found.expiresAt()) {
                pendingByRelay.remove(relay);
                return "REQUEST_EXPIRED";
            }
            if (!found.id().equals(inResponseTo))
                return "IN_RESPONSE_TO_MISMATCH";
            pendingByRelay.remove(relay);
            return "MATCH";
        }
    }

    static boolean cookieSent(String sameSite, String method,
                              boolean crossSite, boolean topLevel,
                              boolean https) {
        return switch (sameSite) {
            case "Strict" -> !crossSite;
            case "Lax" -> !crossSite ||
                (topLevel && "GET".equals(method));
            case "None" -> https;
            default -> false;
        };
    }

    public static void main(String[] args) {
        Login tabA = new Login("_REQ-A", "R-A", "SID-1", 100);
        Login tabB = new Login("_REQ-B", "R-B", "SID-1", 100);

        System.out.println("LAX_CROSS_POST=" +
            cookieSent("Lax", "POST", true, true, true));
        System.out.println("LAX_CROSS_GET=" +
            cookieSent("Lax", "GET", true, true, true));
        System.out.println("STRICT_CROSS_GET=" +
            cookieSent("Strict", "GET", true, true, true));
        System.out.println("NONE_CROSS_POST_HTTPS=" +
            cookieSent("None", "POST", true, true, true));
        System.out.println("NONE_CROSS_POST_HTTP=" +
            cookieSent("None", "POST", true, true, false));

        SinglePendingSessionRepository single =
            new SinglePendingSessionRepository();
        single.save(tabA);
        System.out.println("ONE_TAB=" +
            single.callback("SID-1", "_REQ-A"));
        System.out.println("COOKIE_LOST=" +
            single.callback(null, "_REQ-A"));

        single.save(tabA);
        single.save(tabB);
        System.out.println("TAB_A_AFTER_B=" +
            single.callback("SID-1", "_REQ-A"));
        System.out.println("TAB_B=" +
            single.callback("SID-1", "_REQ-B"));

        PerTransactionRepository multi =
            new PerTransactionRepository();
        multi.save(tabA);
        multi.save(tabB);
        System.out.println("MULTI_A=" +
            multi.callback("R-A", "_REQ-A", "SID-1", 10));
        System.out.println("MULTI_B=" +
            multi.callback("R-B", "_REQ-B", "SID-1", 10));
        System.out.println("REPLAY_A=" +
            multi.callback("R-A", "_REQ-A", "SID-1", 11));

        multi.save(new Login("_REQ-C", "R-C", "SID-1", 50));
        System.out.println("WRONG_BROWSER=" +
            multi.callback("R-C", "_REQ-C", "SID-EVIL", 10));
        System.out.println("WRONG_ID=" +
            multi.callback("R-C", "_REQ-OTHER", "SID-1", 10));
        System.out.println("EXPIRED=" +
            multi.callback("R-C", "_REQ-C", "SID-1", 50));
        System.out.println("NO_RELAY=" +
            multi.callback(null, "_REQ-C", "SID-1", 20));
    }
}
```

Biên dịch và chạy:

```bash
javac SamlCorrelationDiagnosticsDemo.java
java SamlCorrelationDiagnosticsDemo
```

**Stdout xác định:**

```text
LAX_CROSS_POST=false
LAX_CROSS_GET=true
STRICT_CROSS_GET=false
NONE_CROSS_POST_HTTPS=true
NONE_CROSS_POST_HTTP=false
ONE_TAB=MATCH
COOKIE_LOST=COOKIE_MISSING
TAB_A_AFTER_B=IN_RESPONSE_TO_MISMATCH
TAB_B=MATCH
MULTI_A=MATCH
MULTI_B=MATCH
REPLAY_A=REQUEST_NOT_FOUND
WRONG_BROWSER=BROWSER_BINDING_MISMATCH
WRONG_ID=IN_RESPONSE_TO_MISMATCH
EXPIRED=REQUEST_EXPIRED
NO_RELAY=RELAY_MISSING
```

### 15.1. Giải nghĩa output

- `LAX_CROSS_POST=false`: explicit Lax không gửi cookie trên cross-site POST theo mô hình.
- `LAX_CROSS_GET=true`: top-level safe GET có thể mang cookie.
- `STRICT_CROSS_GET=false`: Strict ngăn cross-site navigation.
- `NONE_CROSS_POST_HTTPS=true`: None+Secure có thể gửi cookie trên HTTPS, nhưng browser settings còn ảnh hưởng.
- `COOKIE_LOST`: session không tới server, chưa thể so request ID.
- `TAB_A_AFTER_B`: request B ghi đè A trong cùng session; InResponseTo mismatch.
- `MULTI_A`/`MULTI_B`: per-transaction storage minh họa hai tabs không ghi đè.
- `REPLAY_A`: request đã được consume, không dùng lại.
- `WRONG_BROWSER`: RelayState đúng vẫn không đủ khi browser binding sai.
- `WRONG_ID`: response không trả lời pending AuthnRequest.
- `EXPIRED`: transaction không tồn tại vô hạn.

**Giới hạn quan trọng:** `HashMap` không thread-safe/cluster-safe. `browserSession` và boolean cookie mô phỏng dữ liệu tin cậy; trong production không được đọc chúng từ HTTP query/header do attacker tự khai. Mã demo xóa request khi correlation match **trước khi kiểm SAML signature**, nên **chỉ là mô phỏng chính sách**; implementation thật cần protocol validator, atomic consumption, replay protection và security review đầy đủ.

## 16. Ma trận kiểm thử nguyên nhân và security regressions

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| CK01 | SameSite=Lax explicit + SAML cross-site POST. | Browser thường exclude JSESSIONID. |
| CK02 | SameSite=Strict + cross-site GET. | Cookie excluded, không có session. |
| CK03 | SameSite=None nhưng không có Secure. | Browser reject cookie theo policy. |
| CK04 | Secure cookie + callback HTTP. | Cookie không gửi, yêu cầu public HTTPS. |
| CK05 | Cookie Path=/app nhưng ACS=/login/saml2/sso. | Cookie không gửi do Path. |
| CK06 | Cookie host A, ACS host B. | Domain/host mismatch. |
| CK07 | Browser included cookie, ingress strip Cookie. | Backend không nhận cookie; fix ingress. |
| CK08 | Browser included cookie, Redis session expired. | App không thấy session; deny safely. |
| CK09 | Browser iframe/third-party cookie blocked. | Diagnose privacy settings, top-level flow. |
| CK10 | IdP MFA lâu hơn session TTL. | Request expired, không accept unsolicited. |
| CK11 | Explicit Lax và default Lax có hành vi khác. | Không dựa vào grace window. |
| CK12 | Hai cookies JSESSIONID ở khác Path. | Phát hiện ambiguity, không dùng sai session. |
| RE01 | Không có outbound AuthnRequest. | Xác định initiation/IdP-initiated flow. |
| RE02 | AuthnRequest created nhưng repository save failed. | Fail closed, không bypass InResponseTo. |
| RE03 | Save A, callback cookie absent. | Repository not found, reason cookie. |
| RE04 | Save A, callback cookie present nhưng session absent. | TTL/eviction/node/namespace. |
| RE05 | Save A, session present nhưng request absent. | Remove/overwrite/repo mismatch. |
| RE06 | Save A, save B same session, callback InResponseTo A. | Detect mismatch, reject. |
| RE07 | Per-transaction repository, 2 tabs. | Cả hai đúng một lần, replay bị từ chối. |
| RE08 | RelayState inbound khác outbound. | Reject, không open redirect. |
| RE09 | Cache lookup đúng RelayState nhưng wrong browser. | Reject login CSRF/cross-browser injection. |
| RE10 | Cache record expired. | Reject, no indefinite TTL. |
| RE11 | Duplicate ACS response. | Atomic replay/consumption reject. |
| RE12 | Repository remove được gọi hai lần. | Detect duplicate filter/side effect. |
| RE13 | Node A save, Node B load không shared session. | Not found, fix distributed storage. |
| RE14 | Node B session deserialize error. | Explicit fail, no fallback. |
| RE15 | Session rotates sau SAML success. | Không coi là root cause trước auth. |
| RE16 | Session invalidates trước callback. | Missing request, start fresh login. |
| SA01 | Wrong IdP Issuer. | Reject dù InResponseTo match. |
| SA02 | Wrong signature/trust cert. | Reject. |
| SA03 | Wrong AudienceRestriction. | Reject. |
| SA04 | Wrong Destination/Recipient. | Reject, kiểm ACS/metadata. |
| SA05 | Conditions expired. | Reject, kiểm clock skew/NTP. |
| SA06 | Assertion replay trên pod khác. | Shared replay store reject. |
| SA07 | IdP-initiated response tới SP-only app. | Reject theo policy. |
| SA08 | SAML valid, local account DISABLED. | Deny local admission. |
| SA09 | SAML valid, thiếu reports:read. | 403 business authorization. |
| PX01 | ACS POST bị CSRF/WAF chặn trước SAML filter. | Fix narrow matcher, không tắt CSRF toàn app. |
| PX02 | Ingress rewrite https→http trong public ACS. | Correct trusted forwarded headers. |
| PX03 | Callback tới staging còn request tạo ở prod. | Reject; sửa IdP registration. |
| PX04 | Multi-tab + multi-node + duplicate callbacks. | Không overwrite/leak session, đúng replay policy. |

**Test phải có cả happy path lẫn negative path**. Không đánh dấu QA PASS cho một cấu hình “đã hết lỗi” nhưng bây giờ chấp nhận response không có correlation/chữ ký.

## 17. Quy trình ứng phó và khắc phục theo nguyên nhân

### Bước 1: xác nhận SSO profile

SP-initiated hay IdP-initiated? Nếu SP-initiated, có outbound AuthnRequest ID không? Nếu IdP-initiated, chính sách unsolicited có được phê duyệt không?

### Bước 2: kiểm evidence ở SP

Có `REQUEST_CREATED` và `REQUEST_SAVED` theo requestRef, sessionRef, registration và node không? Nếu không, sửa initiation matcher/filter/config.

### Bước 3: kiểm browser HTTP callback

ACS đúng URL/method? JSESSIONID included/excluded? SameSite/Domain/Path/Secure/tracking protection? Browser này có iframe không?

### Bước 4: kiểm ingress và session store

Cookie có đi tới backend không? `getSession(false)` có trả session không? Session TTL, invalidation, Redis namespace, node route và serialization có phù hợp không?

### Bước 5: đối chiếu transaction

Request ID khi save A hay B? Response InResponseTo gì? RelayState gì? Repository load A, B hay null? Có tab khác ghi đè hay duplicate callback consume không?

### Bước 6: phân loại SAML validation

Sau correlation, kiểm signature, issuer, audience, recipient, destination, Conditions/SubjectConfirmation/replay; cuối cùng kiểm local account và authorization.

### Bước 7: sửa tối thiểu và kiểm tra lại

- Cookie SameSite bị exclude: sửa SameSite/HTTPS nếu được duyệt hoặc dùng repository phù hợp với browser-binding.
- Cookie scope sai: sửa Path/Domain/host.
- Proxy strip Cookie: fix gateway.
- Session store multi-node: shared storage/consistent TTL.
- Multi-tab overwrite: per-transaction storage + browser binding + atomic consume.
- ACS/registration sai: sửa metadata/IdP/ingress đồng bộ.
- IdP initiated: policy rõ, không bật fallback vô điều kiện.
- Validation khác: sửa trust/clock/user status, **không disable checks**.

### Bước 8: quan sát và regression

Tái hiện một tab, hai tabs, callbacks đảo thứ tự, MFA lâu, session timeout, pod failover, replay, wrong RelayState/InResponseTo, cross-browser injection, wrong issuer và local account disabled.

## 18. Anti-pattern phải tránh

1. Tắt InResponseTo để “sửa login”.
2. Bật chấp nhận unsolicited response từ mọi IdP.
3. Coi RelayState có mặt là đủ chứng minh browser ownership.
4. Dùng RelayState như open redirect URL tùy ý.
5. Cache request by RelayState nhưng không browser-binding.
6. Dùng một request per session khi cần nhiều tabs đồng thời mà không test.
7. Chỉ tăng session TTL vô hạn.
8. Tắt session fixation protection vì Session ID đổi sau auth.
9. Bỏ signature/Audience/Recipient validation vì cookie đã có.
10. Dùng HTTPS nội bộ làm chứng cứ callback public đúng URL.
11. Trust forwarded headers do browser tự khai.
12. Không test SameSite trong POST, chỉ test GET.
13. Bật SameSite=None rồi tắt CSRF cho toàn app.
14. Coi cookie included đồng nghĩa session còn sống.
15. Coi session sống đồng nghĩa pending request còn đó.
16. Tự gọi removeAuthnRequest khi debug.
17. Log raw SAMLResponse, RelayState, JSESSIONID hoặc NameID.
18. Dùng local session map trên mỗi pod trong cluster mà không có affinity/failover.
19. Nhầm Response ID với AuthnRequest ID.
20. Coi local 403 do permission là lỗi InResponseTo.

## 19. Checklist nghiệm thu trước production

1. AuthnRequest thật sự được tạo và lưu bằng repository đã biết version.
2. Có safe requestRef, relayRef, registration, node/sessionRef để ghép trace.
3. Browser callback đến đúng ACS HTTPS như metadata.
4. Browser DevTools xác nhận cookie included/excluded và reason.
5. Cookie SameSite xét đúng cross-site POST và browser privacy policy.
6. SameSite=None nếu sử dụng có Secure/HTTPS và CSRF business đầy đủ.
7. Cookie Domain/Path/name/lifetime bao phủ ACS, không conflict.
8. Gateway không strip Cookie và không tin attacker forwarded headers.
9. Backend phân biệt Cookie present, Session present và PendingRequest found.
10. Session store chia sẻ đúng giữa pods và có TTL/serialization phù hợp.
11. Multi-tab không overwrite AuthnRequest hoặc policy có fallback an toàn.
12. Cache request by RelayState có browser-binding, one-time consume và chống login CSRF.
13. Wrong InResponseTo/RelayState/issuer/audience/recipient đều bị từ chối.
14. IdP-initiated SSO có chính sách riêng và không là fallback cho missing request.
15. Spring probe không tạo session khi debug và không log raw secrets.
16. ACS filter/CSRF matcher đúng phạm vi, không mở business routes.
17. Đã test multi-node failover, Redis outage, MFA dài và request expiry.
18. Đã kiểm SAML signature/Conditions/replay và local account authorization.
19. Logs/audit/metrics không có raw assertions/cookies/user secrets.
20. Không thay security validation để đổi lấy login success rate.

## 20. Tự kiểm tra kiến thức

1. **AuthnRequest ID và InResponseTo quan hệ thế nào?** — InResponseTo trỏ về AuthnRequest ID.
2. **RelayState có đủ để xác thực browser không?** — Không; cần binding.
3. **Spring Security mặc định lưu AuthnRequest ở đâu?** — HttpSessionSaml2AuthenticationRequestRepository.
4. **Tại sao explicit SameSite=Lax có thể làm mất cookie?** — Cross-site POST từ IdP không phải top-level safe GET.
5. **SameSite=None yêu cầu gì?** — Secure/HTTPS và CSRF business; còn browser privacy policy.
6. **Cookie included nhưng Session null là gì?** — Store TTL/eviction/node/namespace/invalidation.
7. **Session có nhưng load B trong khi InResponseTo A?** — Multi-tab overwrite hoặc mapping nhầm.
8. **Có nên bỏ InResponseTo không?** — Không, vì bảo vệ login correlation.
9. **Cache theo RelayState phải thêm gì?** — Browser binding, TTL, atomic consumption và replay policy.
10. **Session ID rotate sau success có sai?** — Không, có thể là session fixation protection đúng.
11. **IdP-initiated login khác SP-initiated ở đâu?** — Không có AuthnRequest gốc, cần profile policy riêng.
12. **Bằng chứng tốt nhất cho cookie excluded?** — Browser DevTools ACS POST với lý do.
13. **Bằng chứng tốt nhất cho multi-tab overwrite?** — Save A, Save B trong cùng session; callback A load B.
14. **Multi-node cần gì?** — Shared session/request state, TTL, atomicity và failover QA.
15. **Khi InResponseTo match nhưng chữ ký fail phải làm gì?** — Sửa trust/IdP validation, không chỉnh SameSite.
16. **Tại sao không dùng getSession() trong probe?** — Có thể tạo session mới gây sai kết luận.
17. **Có được log raw SAMLResponse để debug?** — Không, có assertion và PII.
18. **Tại sao cookie scope quan trọng?** — Domain/Path/Secure quyết định browser gửi trên ACS hay không.
19. **SAML validate OK mà local account disabled thì sao?** — Deny local admission.
20. **Thứ tự debug nhanh nhất?** — Outbound/save → browser cookie → ingress/session → request load/ID match → SAML validator → local authz.

## Tài liệu tham khảo

- [Spring Security — Producing SAML2 AuthnRequests: HttpSession repository, CacheSaml2AuthenticationRequestRepository, RelayState trade-offs](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML2 Responses and OpenSAML provider](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security issue #14793 — Multi-tab AuthnRequest overwrite in session (version-specific)](https://github.com/spring-projects/spring-security/issues/14793)
- [Spring Boot Servlet Web Applications — SameSite session cookie configuration](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [MDN — Set-Cookie: SameSite, Secure, default-Lax grace](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Using HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Secure Cookie Configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- [Spring Security — Session Management and Fixation Protection](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)