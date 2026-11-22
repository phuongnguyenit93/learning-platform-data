# Kiểm thử RelayState, mất phiên và hai luồng đăng nhập đồng thời

Trong **Spring Security SAML2 Service Provider (SP)**, một `SAMLResponse` có chữ ký hợp lệ vẫn có thể phải bị từ chối nếu ứng dụng **không tìm lại được AuthnRequest ban đầu**, browser không gửi session cookie lúc IdP POST về ACS, `RelayState` bị thay đổi hoặc **hai tab đồng thời khởi tạo SSO** khiến thông tin pending request bị ghi đè.

Bài này hướng dẫn thiết kế và kiểm thử ba nhóm lỗi thường bị nhầm với “IdP không ổn định”:

1. **RelayState** bị sửa, thiếu, trùng, nhầm với `InResponseTo` hoặc bị dùng làm open redirect.
2. **Mất phiên** bởi `SameSite` cookie, session TTL, logout, session rotation, reverse proxy hoặc nhiều SP nodes.
3. **Hai luồng đăng nhập đồng thời** trên cùng session: AuthnRequest A/B, response đến đảo thứ tự, repository overwrite, race condition và replay.

**Nguyên tắc bảo mật:** mỗi response phải được xác minh bằng đúng IdP registration, chữ ký, issuer, audience, recipient, thời hạn, subject confirmation và correlation cần thiết. Một flow đã mất correlation **không được tự chuyển thành IdP-initiated/unsolicited login**; nếu repository không thể chứng minh flow hợp lệ, **fail closed**.

Bài thuộc **Spring Security – federation → Kiểm thử SAML2**. Bao gồm lý thuyết chuẩn OASIS, phiên bản và các repository của Spring Security, test design theo Given–When–Then, ví dụ Java 17 chạy thuần JDK, ma trận kiểm thử bảo mật, runbook và nguồn chính thức.

## 1. SAML SP-initiated hoạt động qua hai nửa giao dịch

~~~text
Browser                          Spring SP                         IdP
  |                                 |                               |
  | GET /saml2/authenticate/corp    |                               |
  |-------------------------------->|                               |
  |                            AuthnRequest ID=REQ-A                |
  |                            RelayState=R-A                       |
  |                            Save pending request                 |
  |<----- Redirect with SAMLRequest + RelayState -------------------|
  |---------------------------------------------------------------->|
  |                                               Authenticate user |
  |<------------------------------- HTML form for ACS POST ---------|
  | POST /login/saml2/sso/corp       |                               |
  | SAMLResponse InResponseTo=REQ-A  |                               |
  | RelayState=R-A                  |                               |
  |-------------------------------->|                               |
  |                              Load pending                       |
  |                              Validate SAML                      |
  |                              One-time consume                   |
  |<------------------------ Local session + redirect -------------|
~~~

Trong Spring Security, `Saml2WebSsoAuthenticationRequestFilter` sinh `AuthnRequest` và lưu thông tin vào `Saml2AuthenticationRequestRepository`. Khi ACS nhận POST, `Saml2WebSsoAuthenticationFilter` và `Saml2AuthenticationTokenConverter` tìm registration/request phù hợp, rồi OpenSAML provider kiểm response.

**Điểm cần test:** việc SAML signature verify được và việc tìm lại pending login transaction là **hai bảo đảm độc lập**. Không kết luận chữ ký sai chỉ vì `InResponseTo` lookup thất bại.

## 2. RelayState có vai trò gì?

**RelayState** là tham số của SAML HTTP bindings, thường chứa **opaque handle** để SP liên kết callback với trạng thái của yêu cầu ban đầu và phục hồi mục tiêu điều hướng an toàn sau login. IdP thường phản hồi nguyên giá trị RelayState đã nhận cùng với AuthnRequest.

Ví dụ request minh họa:

~~~http
POST /login/saml2/sso/corp HTTP/1.1
Host: portal.example.test
Content-Type: application/x-www-form-urlencoded

SAMLResponse=BASE64_SIGNED_FIXTURE&RelayState=R-A
~~~

Trong ví dụ này, `BASE64_SIGNED_FIXTURE` chỉ là ký hiệu, **không phải assertion dùng được**.

**RelayState không phải**:
- User ID hay bằng chứng xác thực.
- SAML `Response.InResponseTo`.
- JWT/OAuth token hoặc session cookie.
- Chứng cứ rằng IdP đã ký parameter bên ngoài SAML XML.
- Bằng chứng browser hiện tại khởi tạo flow nếu chỉ lookup cache toàn cục.
- URL redirect đáng tin chỉ vì được IdP echo.
- Quyền tenant hoặc local `GrantedAuthority`.

Mỗi use case phải có **server-side expected value**, integrity/correlation và quyền truy cập tài nguyên được kiểm độc lập.

## 3. Ràng buộc của OASIS đối với RelayState

Theo OASIS SAML 2.0 Bindings cho HTTP Redirect/POST, RelayState **không vượt quá 80 byte**, **nên được bảo vệ tính toàn vẹn**, và responder phải phản hồi **đúng giá trị** đã được gửi kèm request theo binding phù hợp.

**80 byte khác 80 ký tự**: UTF-8 có ký tự chiếm nhiều byte. Sử dụng token ngẫu nhiên ASCII/URL-safe ngắn, tránh nhồi JSON, URL dài, email hoặc PII. Test cả trường hợp vượt giới hạn chỉ vì Unicode.

**Chú ý chữ ký:** XML signature trên Response/Assertion **không tự bảo vệ form field RelayState** nằm ngoài XML. HTTP Redirect binding có cơ chế ký query parameters bao gồm RelayState khi dùng chữ ký binding; HTTP POST thường đòi cơ chế integrity/correlation riêng. Không viết test giả định mọi RelayState đã ký bởi IdP.

## 4. RelayState khác InResponseTo như thế nào?

| Trường | Nơi xuất hiện | Ý nghĩa |
| --- | --- | --- |
| `AuthnRequest.ID` | XML request do SP tạo | ID giao dịch được phát |
| `RelayState` | HTTP query/form binding | Tham chiếu trạng thái/return target |
| `Response.InResponseTo` | SAMLResponse XML | Response trả lời AuthnRequest nào |
| `SubjectConfirmationData.InResponseTo` | SAML Assertion | Ràng buộc bearer subject với request |
| `Response.ID` / `Assertion.ID` | SAML XML | Replay detection |
| `Destination` | SAML Response | Điểm nhận response |
| `Recipient` | SubjectConfirmationData | ACS của SP |
| `AudienceRestriction` | Assertion Conditions | SP entityID được chấp nhận |

**Bất biến kiểm thử:** nếu `RelayState=R-A` nhưng `InResponseTo=REQ-B` thì **reject**, ngay cả khi cả hai đang có record pending. Ngược lại, `InResponseTo=REQ-A` nhưng RelayState bị thay thành R-B cũng không được ghép tùy tiện.

**Không lấy một trường thay thế cho trường kia** chỉ vì tên ID trông tương tự.

## 5. Cấu trúc một pending authentication request

Một bản ghi logic nên giữ:

~~~text
PendingSamlLogin:
  opaque_relay_state = R-A
  authn_request_id   = REQ-A
  registration_id    = corp
  expected_idp       = urn:corp:idp
  expected_sp        = urn:portal:sp
  expected_acs       = https://portal.example.test/login/saml2/sso/corp
  created_at         = T0
  expires_at         = T0 + bounded TTL
  browser_binding    = session/binding handle (khi thiết kế hỗ trợ)
  safe_return_path   = /invoices
  consumed           = false
~~~

**Không dùng raw RelayState làm unique key toàn hệ thống nếu không có collision/namespace policy**. Chọn random handle đủ entropy, giới hạn TTL/max pending count, reject duplicate và phân tách registration/browser context.

**Không đưa return URL do client gửi trực tiếp vào redirect sau login.** Nếu lưu URL, giữ relative path hoặc allowlisted origin trong server-side state; kiểm path canonicalization, scheme và domain.

## 6. Request repository trong Spring Security

Các thành phần:

- `Saml2WebSsoAuthenticationRequestFilter`: tạo AuthnRequest.
- `AbstractSaml2AuthenticationRequest`: dữ liệu request/binding đã tạo.
- `Saml2AuthenticationRequestRepository`: interface `saveAuthenticationRequest`, `loadAuthenticationRequest` và `removeAuthenticationRequest`.
- `HttpSessionSaml2AuthenticationRequestRepository`: mặc định theo tài liệu Spring; lưu pending request trong `HttpSession`.
- `CacheSaml2AuthenticationRequestRepository`: có từ Spring Security **6.5**, cho phép cache-based lookup liên quan RelayState khi không muốn dựa session.
- `Saml2WebSsoAuthenticationFilter`: nhận SAMLResponse.
- `Saml2AuthenticationTokenConverter`: resolve registration và pending request.
- OpenSAML authentication provider: kiểm chữ ký và các SAML constraints.

**Không mặc định mọi release có cùng behavior multi-tab hoặc cùng provider OpenSAML.** Spring Security 6.x và 7.x thay đổi APIs; code phải được đối chiếu Javadoc/BOM đang dùng.

## 7. Bảo đảm khi lưu pending request trong HttpSession

Nếu browser A khởi tạo request và pending nằm trong session của A, response được đưa sang browser B có session khác **thường không tìm được pending**. Đây là một lớp giảm nguy cơ **login fixation/login CSRF**.

Ngược lại, nếu chỉ dùng RelayState làm key vào cache toàn cục, hệ thống có thể biết request từng do SP tạo nhưng **không tự biết nó có xuất phát từ browser đang nhận response hay không**. Spring Security document nêu rõ trade-off của cache repository.

Vì vậy kiểm thử phải phân biệt:
- **Correlation:** response khớp một request SP tạo.
- **Browser origin binding:** response khớp **flow của browser hiện tại**.
- **Cryptographic validation:** IdP/Assertion được xác minh đúng.
- **Authorization:** user/tenant/resource có quyền.

Bốn lớp này **không thay thế nhau**.

## 8. Mất session không chỉ có một nguyên nhân

**Mất cookie trong browser:** session vẫn tồn tại ở backend nhưng ACS POST không mang `JSESSIONID`. Nguyên nhân thường là SameSite, Domain, Path, Secure hoặc proxy origin.

**Session bị hủy/hết hạn:** IdP mất nhiều thời gian MFA; session timeout, logout, session invalidation/rotation trước callback hoặc ứng dụng restart.

**Không nhìn thấy session trên node khác:** Node A lưu pending, callback đến Node B; không có Spring Session/shared store, sticky routing lỗi, serializer/Redis outage.

**Pending bị ghi đè:** Session vẫn đúng nhưng lưu một request B mới, nên record của A biến mất.

Tất cả có thể cho triệu chứng `InResponseTo mismatch` hoặc repository trả `null`. **Không được sửa bằng cách bỏ InResponseTo/cho unsolicited login mặc định.**

## 9. Cookie SameSite trong SAML POST binding

IdP thường gửi SAML Response bằng **HTML form HTTP POST** từ domain khác tới SP ACS.

- `SameSite=Strict`: browser không gửi cookie trong cross-site navigation như vậy.
- `SameSite=Lax`: thường không gửi cookie trong cross-site POST, dù có browser-specific ngoại lệ với cookie không khai báo attribute.
- `SameSite=None; Secure`: thường cho phép cookie được gửi trong cross-site POST trên HTTPS nếu browser policy chấp nhận; đồng thời tăng nhu cầu CSRF assessment.

Spring Boot configuration minh họa **phải được review trong app có browser cookies**:

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        same-site: none
~~~

**Không hứa cấu hình này giải quyết mọi browser:** privacy policies, alternate proxy domains và các cookie restrictions vẫn ảnh hưởng. Test bằng DevTools browser thật: SP có `Set-Cookie`, ACS POST có `Cookie` hay không, session có khôi phục được không.

**Không chuyển `secure:false`, dùng HTTP hoặc tắt mọi CSRF controls** chỉ để làm login pass.

## 10. Thiết kế Given–When–Then cho luồng cơ bản

**Given:** browser có session S, registration Corp, pending record (S, R-A, REQ-A, corp).

**When:** IdP Corp trả signed response có `InResponseTo=REQ-A` và echo `RelayState=R-A` tới ACS Corp, session cookie còn được gửi.

**Then:**
1. Repository tìm đúng pending.
2. Spring chọn đúng Corp RelyingPartyRegistration.
3. Signature, issuer, destination, recipient, audience, subject confirmation và time conditions đều hợp lệ.
4. Pending record được consume theo policy.
5. Authentication chứa đúng verified principal, tenant/roles được application mapping.
6. Browser chuyển tới safe return path.
7. Gửi lại cùng SAMLResponse không tạo login mới.

**Assertion bằng HTTP 302 là chưa đủ** vì failure handler cũng có thể redirect. Kiểm SecurityContext/identity/tenant, saved request và replay behavior.

## 11. RelayState tampering: test những gì?

| Tình huống | Kỳ vọng |
| --- | --- |
| Đổi một ký tự của R-A | Reject |
| Bỏ RelayState | Reject ở SP-initiated flow cần binding |
| RelayState rỗng thay giá trị đã lưu | Reject |
| RelayState chưa từng được SP phát | Reject |
| Dùng RelayState đã consumed | Replay reject |
| Dùng RelayState của tab B với Response A | Reject |
| RelayState chứa URL external | Không open redirect |
| RelayState chứa CRLF/control chars | Reject/sanitize |
| Hai form fields RelayState có giá trị khác nhau | Reject ambiguous input |
| RelayState bị URL-encoded khác nghĩa | Không canonicalize tạo collision |
| RelayState dài quá 80 byte | Reject hoặc controlled failure |
| RelayState có Unicode >80 byte nhưng <80 characters | Byte-aware limit |
| RelayState cũ nhưng XML signature hợp lệ | Không tự tạo Authentication |
| RelayState đúng nhưng SAML Issuer sai | Reject |
| RelayState đúng nhưng Assertion expired | Reject |

Bảo đảm quan trọng nhất: **input bất thường không biến thành identity đã xác thực hay redirect tới domain của attacker**.

## 12. Hai tab khởi tạo SSO trong cùng session

~~~text
Browser session S
  Tab A: AuthnRequest ID=REQ-A, RelayState=R-A
  Tab B: AuthnRequest ID=REQ-B, RelayState=R-B

Timeline:
  A started at t0
  B started at t1
  Response B arrives at t2
  Response A arrives at t3
~~~

**Nếu repository chỉ có một pending slot trên session**, B có thể ghi đè A. Response B có thể thành công; Response A phải fail closed khi không còn request khớp. Tình huống này đã được báo cáo với `HttpSessionSaml2AuthenticationRequestRepository`; hãy test đúng behavior của version hiện tại.

**Nếu repository hỗ trợ nhiều pending records**, có thể giữ A và B riêng theo RelayState/request ID và browser binding. Response đến bất kỳ thứ tự nào cũng phải resolve đúng; mỗi pending tiêu thụ một lần. Nhưng nếu A/B đăng nhập **hai users khác nhau**, product phải có chính sách SecurityContext/session rõ, không để role của A gắn cho principal B.

**Hai tab không bắt buộc cùng thành công**. Mục tiêu tối thiểu là bảo toàn trust và identity.

## 13. Hai flows khác IdP hoặc khác tenant

Thử:

~~~text
Tab A:
  registration=corp
  expected IdP=urn:corp:idp
  request=REQ-A
  relay=R-A
  tenant=north

Tab B:
  registration=partner
  expected IdP=urn:partner:idp
  request=REQ-B
  relay=R-B
  tenant=south
~~~

Các phản hồi phải bị từ chối:
- Partner ký Assertion nhưng request thuộc Corp.
- `R-A` đi với `InResponseTo=REQ-B`.
- Response B đến Corp ACS và hệ thống tự đổi sang Partner để “chữa”.
- User cùng email ở hai IdPs bị auto-link.
- Role `ROLE_ADMIN` của tenant South được cấp cho North.
- Browser đang có session user A nhưng callback B khiến session chứa A principal + B roles.

**Correlation phải bao gồm đúng registration, IdP entityID, audience, subject và tenant authorization**, không chỉ RelayState.

## 14. Thứ tự response không được quyết định tính hợp lệ

IdP có thể yêu cầu MFA, dẫn đến tab A chậm hơn tab B. Không thể bảo đảm Response A đến trước chỉ vì AuthnRequest A được tạo trước.

Test hai chiều:
- A tạo trước, response **B→A**.
- A tạo trước, response **A→B**.
- B login fail, A thành công.
- A timeout, B còn hiệu lực.
- A logout session trong khi B đang ở IdP.
- A và B cùng hoàn tất gần như đồng thời.

**Không có đường “nhận response mới nhất rồi cho user vào”** nếu request correlation sai. Với single-slot repository, response cũ phải fail closed; với multi-slot, mỗi callback dùng đúng record và có session semantics nhất quán.

## 15. Race condition khi cùng response được POST hai lần

Một replay race có thể xảy ra trên hai SP nodes:

~~~text
Node A                       Node B
  load pending R-A -> found    load pending R-A -> found
  validate SAML                validate SAML
  create Authentication        create Authentication
  remove R-A                   remove R-A
~~~

Nếu xử lý **load→validate→remove** không bảo đảm one-time theo kiến trúc thực, cả hai có thể chấp nhận. Cần **atomic consume hoặc replay controls tương đương**, và kiểm Response/Assertion IDs đã sử dụng theo chính sách.

**Cẩn thận:** một atomic remove trong cùng JVM không bảo đảm atomic giữa nhiều pods. Redis/DB cần primitive transactional hoặc compare-and-delete, key scoping và TTL. Không test concurrency chỉ bằng `Thread.sleep`; dùng `CountDownLatch`, `CyclicBarrier` hoặc công cụ load test đồng bộ.

## 16. CacheSaml2AuthenticationRequestRepository: lợi ích và trade-off

Từ **Spring Security 6.5**, `CacheSaml2AuthenticationRequestRepository` có thể được dùng thay session-backed repository để lookup AuthnRequest bằng cache/RelayState. Tài liệu mô tả nó hữu ích khi `SameSite=Strict` khiến session-associated request không tìm lại được.

Nhưng security trade-off **rất thực**:
- SP biết AuthnRequest đó từng được tạo bởi SP.
- SP **không nhất thiết biết browser hiện tại là nơi khởi tạo request đó**.

Đây là cửa ngõ **login fixation** nếu attacker khởi tạo flow hợp lệ cho account của mình rồi chuyển SAMLResponse/RelayState sang browser nạn nhân.

Nếu dùng cache repository:
1. Bổ sung hoặc chứng minh browser/transaction binding phù hợp threat model.
2. Opaque key đủ entropy, TTL ngắn và one-time atomic consume.
3. Bind record với exact registration/IdP/expected ACS.
4. Không dùng InResponseTo tự khai báo làm bằng chứng login gốc.
5. Test cross-browser injection thật.
6. Giới hạn số pending, tránh DoS.
7. Dùng distributed storage nếu chạy nhiều nodes; không mặc định in-memory cache liên node.
8. Có session/role lifecycle sau successful login.
9. Không làm downgrade sang unsolicited assertions khi store unavailable.

**Không đổi từ session sang cache chỉ vì muốn hai tab cùng pass mà chưa qua review login fixation.**

## 17. Mảnh Spring config cho cache repository

Ví dụ dưới đây là **mã dự án Spring Security 6.5+**, không chạy với JDK thuần và **không phải khuyến nghị bật mặc định**:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.authentication.AbstractSaml2AuthenticationRequest;
import org.springframework.security.saml2.provider.service.web.CacheSaml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.web.Saml2AuthenticationRequestRepository;

@Configuration
public class SamlRequestRepositoryConfig {

    @Bean
    Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>
            authenticationRequestRepository() {
        // Chỉ sử dụng sau review browser-binding/login-fixation.
        return new CacheSaml2AuthenticationRequestRepository();
    }
}
~~~

Spring Security có thể tự phát hiện bean repository cho SAML request/response filters theo release. **Kiểm đúng BOM và integration tests** để chắc chắn cả request filter lẫn response converter đều dùng **cùng repository**.

Nếu nhu cầu chỉ là sửa sai cookie trên ACS, có thể giữ `HttpSessionSaml2AuthenticationRequestRepository` mặc định và sửa SameSite/cookie/proxy thay vì chấp nhận trade-off cache.

## 18. Login fixation khi chỉ tra cache theo RelayState

Một negative E2E test đáng có:

~~~text
Attacker browser:
  Tự khởi tạo AuthnRequest qua SP.
  Nhận RelayState R-ATTACK.
  Hoàn tất IdP login bằng account attacker.
  Thu signed SAMLResponse cho request của attacker.

Victim browser:
  Chưa hề bắt đầu SP login.
  Bị đưa đến ACS với response + R-ATTACK.

Kỳ vọng:
  Không được tạo phiên authenticated của attacker cho victim,
  nếu ứng dụng yêu cầu session-origin binding.
~~~

Nếu product chấp nhận unsolicited SAML theo policy, vẫn phải kiểm login-CSRF/response integrity/replay và không khiến victim bị đăng nhập ngoài ý muốn. Không lẫn khả năng nhận một assertion signed với việc đã có **consent/request binding** của browser.

## 19. Mất session do logout, timeout, session rotation

Ba ca này dễ bị nhầm:

**Timeout:** người dùng ở IdP/MFA lâu hơn HTTP session TTL. SP không còn pending. Kỳ vọng: fail closed, thông báo phiên đăng nhập đã hết và cho bắt đầu lại, tránh redirect loop.

**Logout tab khác:** user nhấn logout khi một tab còn ở IdP. Callback cũ không được âm thầm “hồi sinh” session và quyền trước logout ngoài policy.

**Session fixation protection/rotation:** Spring có thể đổi session ID sau authentication thành công; đây là behavior khác với việc session bị invalidate **trước** callback. Nếu custom filter tạo/hủy session quá sớm, pending có thể bị mất.

**Không ép SessionCreationPolicy.STATELESS** cho SAML SP-initiated flow đang cần pending request trong HttpSession mà không thiết kế repository/correlation thay thế.

## 20. Spring Session và nhiều nodes

~~~text
GET /saml2/authenticate/corp -> Node A
  save pending REQ-A vào session S

POST /login/saml2/sso/corp -> Node B
  Node B phải load được session S
  và đúng pending REQ-A
~~~

Có thể dùng Spring Session backed by Redis/JDBC hoặc LB session affinity phù hợp, kèm failover test. Nhưng:
- Sticky sessions không tự cứu khi node A chết.
- Redis shared session lỗi/expired thì SP phải reject.
- Serialization versions không tương thích có thể mất pending.
- Distributed cache consume phải one-time trên **toàn cluster**.
- Proxy phải forward HTTPS public host/schema đúng để ACS/cookie match.
- App không được dùng fallback “skip request correlation” khi session store outage.

**Test cả request trên A, callback trên B và concurrent callbacks trên A/B.**

## 21. Java 17 runnable: mô phỏng single-slot, multi-slot và concurrent consume

Ví dụ này **không thực hiện SAML signature validation**; nó chỉ kiểm **correlation policy**. Kết quả `ACCEPT_CORRELATED` **không phải Authentication thành công**. Production vẫn phải kiểm SAML issuer, signing credentials, audience, destination, recipient, conditions, NameID và replay cache.

Tạo file **SamlRelayStateConcurrencyDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SamlRelayStateConcurrencyDemo {

    record Pending(String session, String relay, String requestId,
                   String registration, long expiresAt) {}

    static class OneSlotRepository {
        private final Map<String, Pending> store = new HashMap<>();

        synchronized void save(Pending pending) {
            store.put(pending.session(), pending);
        }

        synchronized String consume(String session, String relay,
                                    String inResponseTo, String registration) {
            if (session == null) {
                return "DENY_NO_SESSION";
            }
            Pending p = store.get(session);
            if (p == null) {
                return "DENY_UNKNOWN_OR_REPLAY";
            }
            if (!p.relay().equals(relay)) {
                return "DENY_RELAY";
            }
            if (!p.requestId().equals(inResponseTo)) {
                return "DENY_IN_RESPONSE_TO";
            }
            if (!p.registration().equals(registration)) {
                return "DENY_REGISTRATION";
            }
            store.remove(session);
            return "ACCEPT_CORRELATED";
        }
    }

    static class MultiRequestRepository {
        private final Map<String, Map<String, Pending>> store =
                new HashMap<>();

        synchronized void save(Pending p) {
            Map<String, Pending> requests = store.computeIfAbsent(
                    p.session(), key -> new HashMap<>());
            if (requests.putIfAbsent(p.relay(), p) != null) {
                throw new IllegalArgumentException("Duplicate RelayState");
            }
        }

        synchronized String consume(String session, String relay,
                                    String inResponseTo, String registration,
                                    long now) {
            if (session == null) {
                return "DENY_NO_SESSION";
            }
            Map<String, Pending> requests = store.get(session);
            if (requests == null) {
                return "DENY_UNKNOWN_OR_REPLAY";
            }
            Pending p = requests.get(relay);
            if (p == null) {
                return "DENY_UNKNOWN_OR_REPLAY";
            }
            if (now > p.expiresAt()) {
                remove(session, relay, requests);
                return "DENY_EXPIRED";
            }
            if (!p.requestId().equals(inResponseTo)) {
                return "DENY_IN_RESPONSE_TO";
            }
            if (!p.registration().equals(registration)) {
                return "DENY_REGISTRATION";
            }
            remove(session, relay, requests);
            return "ACCEPT_CORRELATED";
        }

        private void remove(String session, String relay,
                            Map<String, Pending> requests) {
            requests.remove(relay);
            if (requests.isEmpty()) {
                store.remove(session);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Pending a = new Pending("S", "R-A", "REQ-A", "corp", 100);
        Pending b = new Pending("S", "R-B", "REQ-B", "corp", 100);

        OneSlotRepository one = new OneSlotRepository();
        one.save(a);
        one.save(b);
        System.out.println("Single-slot A after B: "
                + one.consume("S", "R-A", "REQ-A", "corp"));
        System.out.println("Single-slot B: "
                + one.consume("S", "R-B", "REQ-B", "corp"));

        MultiRequestRepository multi = new MultiRequestRepository();
        multi.save(a);
        multi.save(b);
        System.out.println("Swap InResponseTo: "
                + multi.consume("S", "R-A", "REQ-B", "corp", 10));
        System.out.println("B before A: "
                + multi.consume("S", "R-B", "REQ-B", "corp", 10));
        System.out.println("A after B: "
                + multi.consume("S", "R-A", "REQ-A", "corp", 10));
        System.out.println("Replay A: "
                + multi.consume("S", "R-A", "REQ-A", "corp", 10));
        System.out.println("Lost session: "
                + multi.consume(null, "R-A", "REQ-A", "corp", 10));

        Pending c = new Pending("S", "R-C", "REQ-C", "partner", 12);
        multi.save(c);
        System.out.println("Wrong registration: "
                + multi.consume("S", "R-C", "REQ-C", "corp", 11));
        System.out.println("Expired: "
                + multi.consume("S", "R-C", "REQ-C", "partner", 13));

        Pending race = new Pending("S", "R-RACE", "REQ-RACE", "corp", 100);
        multi.save(race);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        Callable<String> attempt = () -> {
            start.await();
            return multi.consume("S", "R-RACE",
                    "REQ-RACE", "corp", 20);
        };

        try {
            Future<String> first = pool.submit(attempt);
            Future<String> second = pool.submit(attempt);
            start.countDown();
            String x = first.get();
            String y = second.get();
            int accepted = ("ACCEPT_CORRELATED".equals(x) ? 1 : 0)
                    + ("ACCEPT_CORRELATED".equals(y) ? 1 : 0);
            System.out.println("Concurrent replay: accepted="
                    + accepted + ", rejected=" + (2 - accepted));
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SamlRelayStateConcurrencyDemo.java
java SamlRelayStateConcurrencyDemo
~~~

**Stdout chính xác:**

~~~text
Single-slot A after B: DENY_RELAY
Single-slot B: ACCEPT_CORRELATED
Swap InResponseTo: DENY_IN_RESPONSE_TO
B before A: ACCEPT_CORRELATED
A after B: ACCEPT_CORRELATED
Replay A: DENY_UNKNOWN_OR_REPLAY
Lost session: DENY_NO_SESSION
Wrong registration: DENY_REGISTRATION
Expired: DENY_EXPIRED
Concurrent replay: accepted=1, rejected=1
~~~

**Giải thích:** one-slot cho thấy B ghi đè A, nhưng A không bị nhận nhầm. Multi-slot cho phép response đến đảo thứ tự, reject swapped InResponseTo, ngăn replay và không tự nhận mất session. Khi hai threads cùng consume R-RACE, synchronized bảo đảm **một thắng trên một JVM**; kết quả tổng hợp không phụ thuộc scheduler. Hệ multi-node phải dùng transactional/atomic shared store và replay protection khác.

**Code không chứa bộ xác minh SAML**, không xác minh XML/certificates, không tạo Spring SecurityContext, và không dùng được như production AuthenticationProvider.

## 22. Phân biệt test unit, Spring integration và browser E2E

| Tầng | Có thể chứng minh | Không thể tự chứng minh |
| --- | --- | --- |
| Java unit/repository | Exact correlation, TTL, replay, single-slot/multi-slot behavior | Chữ ký SAML thật hoặc browser cookie policy |
| Spring Security MockMvc | Filter wiring, request repository, failure handlers, Authentication | Cross-site browser SameSite thực |
| IdP integration | Signed response, issuer/audience/ACS, InResponseTo | Mọi browser/privacy variation |
| Browser E2E | Session cookie, cross-site POST, two tabs, redirect loop | Atomicity across pods nếu chạy một node |
| Multi-node/load | Shared store, duplicated POST, failover | Đảm bảo app đã kiểm object-level authorization nếu không assert |

**MockMvc test với status 302 không đủ**: lỗi authentication cũng có thể redirect đến trang login. Phải assert không có SecurityContext authenticated trong negative cases, và xác nhận principal/tenant/role chính xác trong positive cases.

## 23. Các lớp Spring cần test trong integration

1. `Saml2WebSsoAuthenticationRequestFilter` phát request với đúng registration.
2. `Saml2AuthenticationRequestRepository` thực sự save/load/remove.
3. `Saml2WebSsoAuthenticationFilter` nhận callback đúng ACS matcher.
4. `Saml2AuthenticationTokenConverter` resolve đúng expected request/registration.
5. OpenSAML provider xác minh chữ ký/issuer/audience/recipient/time.
6. SecurityContext/session sau success không dùng account stale.
7. Authentication failure handler không tạo SecurityContext.
8. Session fixation strategy không xóa pending trước callback.
9. Saved request/redirect target an toàn.
10. Role mapping và tenant membership sau authentication.

Kiểm cùng cấu hình **đang deploy**, không giả định XML Spring Security 5.x giống Java DSL Spring Security 6.x/7.x. Tùy version, OpenSAML4/5 provider và bean wiring khác nhau.

## 24. Fixture cho hai flows A/B

| Thuộc tính | Flow A | Flow B |
| --- | --- | --- |
| Browser | Browser-1 | Browser-1 |
| Session ID | S-100 | S-100 |
| Tab | A | B |
| Registration | corp | corp/partner |
| AuthnRequest ID | REQ-A | REQ-B |
| RelayState | R-A | R-B |
| IdP entityID | urn:corp:idp | urn:corp:idp hoặc urn:partner:idp |
| SP entityID | urn:portal:sp:corp | SP entityID của B |
| ACS | /login/saml2/sso/corp | ACS của B |
| Expiry | T0 + TTL | T1 + TTL |
| Expected local account | Theo verified response A | Theo verified response B |
| Tenant | Theo server policy A | Theo server policy B |

**Fixture phải dùng request IDs khác nhau**, RelayStates random/unique, signing test key pair của IdP riêng và cert tin cậy của SP test. Không đưa production NameID/cookies/assertions vào logs.

## 25. Quy trình E2E theo Given–When–Then

**Case chuẩn:**
- Given một browser session S và IdP test Corp.
- When khởi tạo login, nhận request/RelayState, IdP ký Response khớp.
- Then đúng user được authenticated, pending consumed, không replay.

**Case mất cookie:**
- Given S chứa pending A.
- When browser POST ACS không mang cookie phù hợp.
- Then không có authenticated session, failure được phân loại.

**Case hai tab:**
- Given A và B đã tạo pending trong cùng S.
- When response B đến trước A.
- Then chỉ các responses có pending phù hợp mới được chấp nhận theo behavior repository, không mix user/tenant.

**Case cross-browser:**
- Given attacker A khởi tạo request và victim V chưa từng login.
- When attacker đưa RelayState/Response tới V.
- Then login fixation protections ngăn victim bị gắn session attacker theo security policy.

**Case double-POST:**
- Given cùng response được POST tới hai SP nodes đồng thời.
- Then at-most-once/replay policy được bảo đảm trên toàn cluster.

## 26. Ma trận RelayState và protocol correlation

| # | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 01 | SP phát R-A, IdP echo R-A, Response hợp lệ | Login đúng identity |
| 02 | R-A bị đổi một byte | Reject |
| 03 | RelayState bị bỏ ở callback | Fail closed nếu SP-initiated cần correlation |
| 04 | RelayState rỗng | Reject theo pending contract |
| 05 | RelayState không tồn tại | Reject |
| 06 | RelayState đã consumed | Replay reject |
| 07 | RelayState chứa external URL | Không open redirect |
| 08 | RelayState vượt 80 byte | Không chấp nhận ngoài binding limit |
| 09 | RelayState Unicode >80 byte | Byte-aware validation |
| 10 | RelayState có CRLF | Reject/sanitize |
| 11 | Hai RelayState fields khác giá trị | Reject ambiguous form |
| 12 | RelayState A, InResponseTo B | Reject |
| 13 | RelayState A, wrong registration | Reject |
| 14 | RelayState đúng, IdP issuer sai | Reject |
| 15 | RelayState đúng, SAML signature sai | Reject |
| 16 | RelayState đúng, AudienceRestriction sai | Reject |
| 17 | RelayState đúng, Recipient/Destination sai | Reject |
| 18 | RelayState đúng, Response expired | Reject |
| 19 | Assertion ID replay | Reject |
| 20 | XML Signature Wrapping attempt | Không dùng unsigned claims |

## 27. Ma trận session và cookie

| # | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 21 | Cookie session hợp lệ ở ACS POST | Pending load đúng |
| 22 | SameSite=Strict cross-site POST | Nhận diện session missing; fail closed |
| 23 | SameSite=Lax cross-site POST | Test browser thật; không dựa ngoại lệ |
| 24 | SameSite=None; Secure HTTPS | Cookie hoạt động nếu policy hỗ trợ; CSRF review |
| 25 | Secure cookie qua HTTP ACS | Không cookie, kiến trúc HTTPS cần được sửa |
| 26 | Cookie Domain không khớp ACS | Fail closed |
| 27 | Cookie Path không bao phủ ACS | Fail closed |
| 28 | Session hết TTL lúc user ở IdP | Restart login an toàn |
| 29 | Logout tab khác trước callback | Không hồi sinh session trái policy |
| 30 | App restart làm mất local sessions | Fail closed/shared store |
| 31 | Node A lưu, Node B callback không shared session | Không nhận response |
| 32 | Spring Session shared store đúng | Load pending theo session S |
| 33 | Session ID rotate trước callback | Không accept request nếu mất state |
| 34 | Session fixation protection sau success | Đúng session lifecycle |
| 35 | Redis/DB session store lỗi | Không skip correlation |
| 36 | Browser incognito nhận callback cũ | Reject nếu session-bound |
| 37 | Proxy drop Cookie header | Fail closed |
| 38 | Callback bị đổi public host/scheme | Kiểm cookie và SAML Recipient/Destination |

## 28. Ma trận hai luồng đồng thời và cross-tenant

| # | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 39 | A rồi B cùng session, single-slot | A fail nếu overwritten; B có thể pass |
| 40 | B rồi A cùng session, single-slot | Không accept nhầm |
| 41 | Multi-slot callbacks A rồi B | Correlation đúng từng flow |
| 42 | Multi-slot callbacks B rồi A | Correlation đúng từng flow |
| 43 | A request nhưng callback có RelayState B | Reject |
| 44 | A request nhưng callback có InResponseTo B | Reject |
| 45 | A Corp, B Partner | Không cross-IdP confusion |
| 46 | A North tenant, B South tenant | Không cross-tenant authorization |
| 47 | A user Alice, B user Bob | Session identity-switch policy rõ |
| 48 | Hai ACS POST cùng response cùng JVM | At-most-once |
| 49 | Hai ACS POST cùng response hai nodes | At-most-once distributed |
| 50 | Flow A expired, B còn sống | A fail, B không bị xóa nhầm |
| 51 | A fail, B pending | Không xóa B vô điều kiện |
| 52 | Replay sau success | Reject |
| 53 | Attacker response vào victim browser | Login fixation test |
| 54 | Two tabs + logout/reauthentication | Không resurrect stale session |
| 55 | Signed response cho sai SP entityID | Reject dù RelayState đúng |

**Một hệ thống PASS khi đúng danh tính và quyền**, không chỉ nhiều callback trả HTTP 200. Single-slot có thể cố ý chỉ hỗ trợ một pending request; test phải phản ánh policy đó.

## 29. Kiểm thử concurrency không dựa vào sleep

**Không nên:**

~~~java
// Anti-pattern: timing ngẫu nhiên
Thread.sleep(100);
triggerSecondRequest();
~~~

Dùng `CountDownLatch` hoặc `CyclicBarrier` như chương trình Java 17 ở trên, rồi assert **invariants** thay vì trông chờ task nào chạy trước:
- Chỉ một thread consume được một pending record.
- Không có record bị consume bởi sai registration.
- Replay tiếp theo bị reject.
- Việc xử lý flow A không xóa flow B.
- Khi distributed store lỗi, kết quả fail closed.
- Chỉ tạo authenticated session sau complete validation.

**Lặp test nhiều lần** để lộ race hiếm, kết hợp load test trên hai nodes và network fault injection. Unit test một JVM không chứng minh distributed atomicity.

## 30. Chẩn đoán lỗi bằng dấu hiệu thực tế

| Triệu chứng | Khả năng | Cách xác minh |
| --- | --- | --- |
| InResponseTo mismatch chỉ khi nhiều tabs | Pending overwrite | So request IDs đã pseudonymize |
| Callback không thấy session | SameSite/Domain/Path/TTL | Browser DevTools Set-Cookie/Cookie |
| Một node đăng nhập được, node khác lỗi | Session store/affinity | Multi-node trace |
| RelayState khác ở callback | Encoding/IdP/proxy | Compare exact opaque value trong test |
| 302 lặp vô hạn | Callback thất bại và restart flow | Kiểm failure handler/session cookie |
| Chữ ký sai | IdP key/metadata, không phải RelayState | Kiểm trusted cert và SAML validator |
| User A có roles của B | Session/tenant account linking race | Audit principal + server memberships |
| Cache repo sửa được login nhưng security test fail | Login fixation trade-off | Cross-browser injection test |
| Response replay vẫn login | Consume/replay guard không atomic | Concurrent POST test |
| Đường redirect ra external domain | Trust raw RelayState return URL | Allowlist safe return target |
| Pending mất khi login xong quá nhanh | Custom session invalidation/rotation | Trace session lifecycle |
| SameSite=None nhưng vẫn không cookie | TLS/proxy/browser policy | Test cookie attributes và origin |

**Không sửa tạm** bằng cách bỏ request correlation, chấp nhận tất cả SAML unsolicited, tắt chữ ký hoặc dùng insecure cookies.

## 31. Quan sát và logging có kiểm soát

Nên instrument những trường sau với chính sách tối thiểu hóa dữ liệu:

- Correlation ID chung giữa SP/IdP test và gateway.
- `registrationId` và IdP entityID đã được tin.
- Hashed/pseudonymized `AuthnRequest.ID`, `InResponseTo`, RelayState.
- Repository loại nào, pending FOUND/MISSING/MISMATCH/EXPIRED.
- Session fingerprint không lộ `JSESSIONID`.
- ACS node/pod, browser version và cookie policy.
- Lúc tạo request, lúc callback, TTL còn lại.
- Failure category: COOKIE_MISSING, RESPONSE_REPLAY, REQUEST_OVERWRITTEN.
- Local account ID/tenant/action sau successful authentication.
- SAML signature/protocol validation outcome, không log raw payload.

**Tuyệt đối không dump** SAMLResponse, raw XML chứa NameID/PII, private keys, cookie session ID hoặc RelayState nhạy cảm vào logs/APM/HAR chia sẻ. Test IdP dùng fixtures giả và access controls.

Metrics đề xuất: `saml_relaystate_mismatch_total`, `saml_session_missing_total`, `saml_inresponseto_mismatch_total`, `saml_parallel_login_conflict_total`, `saml_replay_rejected_total`. Đây là đề xuất tùy biến, không mặc định mọi meter có sẵn trong Spring.

## 32. Quy trình triển khai và canary

**Chuẩn bị:**
1. Xác nhận Spring Boot/Security version và repository đang được dùng.
2. Kiểm định RelayState, AuthnRequest ID, expiration/replay.
3. Kiểm session cookie SameSite/Secure/Domain/Path và ACS public HTTPS URL.
4. Xác định business policy: một hay nhiều login flows/outstanding requests.
5. Xác định load balancer, Spring Session, cache consistency và node failover.
6. Chọn IdP test, signing keys/metadata và fake users/tenants.
7. Viết signed fixture test đủ Issuer/Audience/Recipient.
8. Bật logging pseudonymized và failure categories.

**Canary:**
1. Happy path 1 tab.
2. RelayState tamper/unknown/replay/overlong.
3. Session missing sau IdP POST.
4. Hai tab same-session với response đảo thứ tự.
5. Different IdPs/tenants in same session.
6. Double POST cùng response qua hai threads/nodes.
7. Cross-browser login fixation.
8. Key rotation/session TTL/ACS proxy path.
9. Verify user identity/roles/tenant đúng.
10. Rollout sau khi security owner chấp nhận test evidence.

**Khi production incident:**
1. Thu request correlation, release và repository type.
2. Xem cookie đến ACS chưa, session còn tồn tại không.
3. Kiểm tab concurrent và pending overwrite.
4. Kiểm đúng IdP signing cert, ACS/recipient/audience.
5. Không dùng unsolicited fallback để chữa mất phiên.
6. Sửa cookie/store/proxy hoặc repository theo threat review.
7. Chạy lại negative tests trước rollout.
8. Rà soát log PII, purge diagnostics nhạy cảm và kết luận root cause.

## 33. Câu hỏi tự đánh giá

**1. RelayState có chứng minh user đã được IdP xác thực không?**  
Không, đó chỉ là binding/correlation state.

**2. RelayState có cùng nghĩa với InResponseTo không?**  
Không. InResponseTo liên kết XML Response/Assertion với AuthnRequest ID; RelayState tham chiếu state ở HTTP binding.

**3. OASIS giới hạn RelayState thế nào?**  
Không quá 80 **byte** theo HTTP Redirect/POST binding.

**4. Vì sao SAML signed đúng vẫn bị reject khi session mất?**  
SP không còn pending request để chứng minh request correlation/browser session.

**5. Tại sao SameSite có thể ảnh hưởng ACS?**  
IdP POST cross-site có thể không mang session cookie khi SameSite Strict/Lax.

**6. Cache repository có tự đảm bảo browser-origin binding không?**  
Không. Spring docs cảnh báo login fixation trade-off.

**7. Hai tabs cùng session có bắt buộc cùng login thành công không?**  
Không, tùy repository/policy; bắt buộc không lẫn request/identity/tenant.

**8. Nếu B overwrite A, có được bỏ InResponseTo để A login không?**  
Không. A phải fail closed nếu không còn pending A.

**9. Hai threads cùng consume một record cần điều gì?**  
At-most-once/atomic consume và replay protection.

**10. Synchronized trong Java có đủ cho nhiều pods không?**  
Không. Cần distributed atomic mechanism.

**11. Có nên đưa RelayState làm URL redirect luôn không?**  
Không; phải dùng server-stored/allowlisted safe return target.

**12. Session hết lúc IdP yêu cầu MFA thì phải làm gì?**  
Thông báo login transaction expired, bắt đầu lại; không accept unsolicited thay thế.

**13. Test MockMvc có kiểm đầy đủ SameSite behavior không?**  
Không; cần E2E browser thực hiện cross-site POST.

**14. Khi hai IdPs phát cùng NameID/email, có được merge account không?**  
Không tự động; phải có trusted identity linking.

**15. Một response có RelayState hợp lệ nhưng signature sai có pass không?**  
Không, tất cả protocol validations vẫn bắt buộc.

## 34. Checklist production

- [ ] Pending AuthnRequest được lưu với ID/RelayState/registration và TTL rõ.
- [ ] RelayState opaque, random, <=80 bytes, integrity/correlation được bảo đảm.
- [ ] Không dùng raw RelayState làm unvalidated redirect URL hoặc tenant selector.
- [ ] RelayState và InResponseTo được so khớp đúng pair.
- [ ] Mọi SAML Response/Assertion được kiểm signature, Issuer, Audience, Recipient, Destination, Conditions.
- [ ] Response/Assertion replay được ngăn.
- [ ] Session cookie đúng SameSite/Secure/Domain/Path và ACS HTTPS origin.
- [ ] Missing session/pending request fail closed; không tự bật unsolicited SAML.
- [ ] Version và behavior của HttpSessionSaml2AuthenticationRequestRepository đã được kiểm.
- [ ] Có test hai tab A/B cùng session và response đảo thứ tự.
- [ ] Có test single-slot overwrite hoặc multi-slot tùy design.
- [ ] Nếu dùng cache repository, có biện pháp login fixation/browser-binding tương ứng.
- [ ] Consume pending và assertion replay guards có tính atomic theo deployment topology.
- [ ] Spring Session/cache shared state hoạt động nhiều nodes.
- [ ] Session timeout/logout/rotation trước và sau callback được test.
- [ ] Các IdP registrations/tenants không bị mix trong concurrent flows.
- [ ] Spring SecurityContext không giữ sai user/roles sau hai callbacks.
- [ ] Có test cross-browser injection, open redirect và duplicate RelayState fields.
- [ ] E2E signed fixtures, real browser SameSite tests, multi-node load tests.
- [ ] Negative tests khẳng định không có Authentication được tạo.
- [ ] Không log raw SAMLResponse, RelayState, JSESSIONID hay IdP private keys.
- [ ] Có metrics mismatch/replay/missing session/parallel conflict.
- [ ] Sự cố được sửa ở đúng lớp, không hạ signature/recipient/correlation checks.

## 35. Kết luận

**Kiểm thử RelayState, mất phiên và hai luồng SAML đăng nhập đồng thời** là kiểm thử khả năng **gắn kết đúng response với đúng request/browser/registration** và xử lý replay an toàn.

Theo tài liệu Spring Security, repository mặc định `HttpSessionSaml2AuthenticationRequestRepository` lưu pending request trong HTTP session, nhờ đó có một lớp bảo vệ browser-origin nhưng có thể bị mất khi cross-site POST không mang cookie hoặc multi-tab ghi đè pending. `CacheSaml2AuthenticationRequestRepository` từ Spring Security 6.5 là một lựa chọn khác, song **không tự chứng minh response thuộc browser đang đăng nhập**. Vì vậy quyết định dùng cache/multi-slot phải đi kèm threat model chống login fixation, expiration, atomic consume và các tests đúng deployment.

**Một flow chỉ hợp lệ nếu:** RelayState/request correlation đúng, IdP signature/Issuer/Audience/Recipient/Conditions được xác minh, replay guard đạt, local account và tenant/resource policy cho phép. **Nếu mất pending request, hãy fail closed thay vì “nới” SAML validation.**

### Tài liệu tham khảo chính thức

- Spring Security — Producing SAML2 AuthnRequests, session/cache request repository: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Saml2AuthenticationRequestRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationRequestRepository.html
- Spring Security — CacheSaml2AuthenticationRequestRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/CacheSaml2AuthenticationRequestRepository.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- OASIS SAML 2.0 Bindings — HTTP Redirect/POST RelayState: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OASIS SAML 2.0 Technical Overview — SP-initiated SSO and RelayState: https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
