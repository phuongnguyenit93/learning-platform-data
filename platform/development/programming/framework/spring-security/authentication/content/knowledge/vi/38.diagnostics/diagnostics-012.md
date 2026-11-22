# Khóa tài khoản hoặc đăng xuất chưa thu hồi được những phiên, token còn hiệu lực

## 1. Triệu chứng và điều cần chẩn đoán

Một quản trị viên đặt `user.status = LOCKED`, hoặc người dùng nhấn **Đăng xuất** và thấy giao diện trở lại màn hình login. Tuy nhiên, một trình duyệt khác vẫn truy cập được API, một refresh token vẫn đổi ra access token mới, hay một JWT có chữ ký hợp lệ vẫn được Resource Server chấp nhận. Đây là tình huống thường gặp vì **khóa tài khoản, logout phiên hiện tại, thu hồi phiên khác và thu hồi token là những cơ chế khác nhau**.

Đề bài thuộc nhóm **Chẩn đoán** của module Spring Security authentication. Mục tiêu không chỉ biết cách gọi `logout()` hay `deleteById()`, mà còn **xác định chính xác đường xác thực nào còn hiệu lực, vì sao, ai sở hữu nơi lưu trạng thái và cần xác minh kết quả thu hồi ở đâu**.

### Kết quả học tập

1. Truy vết request sau khi khóa/logout để phân biệt HTTP session, remember-me, JWT access token, opaque access token, refresh token, OAuth authorized client và phiên SSO tại IdP.
2. Hiểu **logout mặc định Spring Security Servlet**: xóa `SecurityContext`, invalidate **session hiện tại**, cleanup remember-me/CSRF trong logout flow; không đồng nghĩa “logout all devices”.
3. Tìm nguyên nhân session khác vẫn sống: session registry cục bộ, chỉ mục principal sai/thiếu, Spring Session shared store, request concurrent, cache multi-node, sticky session và authentication được tạo lại.
4. Giải thích tại sao **JWT offline validation** vẫn chấp nhận token đã ký hợp lệ sau khi account bị khóa; xây policy kiểm tra account/version, denylist `jti` hoặc chấp nhận residual lifetime minh bạch.
5. Phân biệt **revoke refresh token/grant ở Authorization Server** với việc thu hồi access token ở các Resource Server; hiểu RFC 7009 và đặc tính `active` trong RFC 7662 introspection.
6. Thiết kế quy trình revoke nhiều loại credential có transaction, outbox, idempotency, kiểm tra race, cache TTL và bằng chứng từ test thật.
7. Viết test tái hiện trước/sau bằng Java 17 và HTTP client riêng biệt, không coi một HTTP `200` hay `302` là chứng cứ tất cả credential đã chết.

**Phạm vi:** Spring Boot 3.x / Spring Security 6.x (Servlet) và các biến thể OAuth2/Resource Server; nơi có WebFlux hoặc Spring Security 7.x cần đối chiếu API tương ứng. Ví dụ Java 17 ở mục 9 chạy độc lập, những snippet Spring Framework cần dependencies/project thực. Không có một Spring method mặc định tự tìm và thu hồi **mọi** JWT, refresh token và IdP session của người dùng.

## 2. Bản đồ vòng đời credential

~~~text
                        LOCAL ACCOUNT
                        userId = u-123
                        status = ACTIVE/LOCKED
                        securityVersion = 12
                                |
                    +-----------+------------+
                    |           |            |
                Browser A   Browser B     Mobile app
                    |           |            |
              HttpSession A HttpSession B   refresh token R1
                    |           |                |
              SecurityContext SecurityContext   Authorization Server
                    |           |                |
                 API session  API session       access JWT J1
                                                   |
                                                   v
                                           Resource Server X/Y
                                              verify signature
                                              iss/aud/exp/...
                                                   |
                                         optional account check
                                         or revocation/denylist

Other independent state:
- SSO session at IdP (OIDC/SAML)
- OAuth2AuthorizedClient access/refresh tokens for downstream API
- persistent remember-me tokens
- device/API keys and passwordless authenticators
~~~

**Điều cần nhớ:** user.status là bản ghi nghiệp vụ; session/authentication có thể đã được tạo khi user còn ACTIVE. Nếu protected request chỉ đọc `SecurityContext` có sẵn, nó không tự gọi lại `UserDetailsService.loadUserByUsername(...)` hoặc kiểm tra `isAccountNonLocked()` mỗi lần. Tương tự, JWT verifier chỉ kiểm tra chữ ký/claim không tự truy vấn user database. Cần **điểm kiểm tra trạng thái** trên từng đường truy cập.

### Ma trận tác động của hành động

| Hành động | Session HTTP hiện tại | Session ở thiết bị khác | JWT access token đã phát | Refresh token | SSO IdP |
| --- | --- | --- | --- | --- | --- |
| `user.status=LOCKED` | Có thể **vẫn tồn tại** nếu không kiểm tra trạng thái | Có thể vẫn tồn tại | Vẫn được verify offline nếu chữ ký/exp hợp lệ | Có thể vẫn đổi token nếu AS không kiểm tra lock | Không tự mất |
| `POST /logout` mặc định Servlet | Invalidate/clear theo logout chain | Không tự xóa | Không tự revoke | Không tự revoke mọi grant | Không tự logout |
| `SessionRegistry.expireNow()` | Chỉ đánh dấu session trong registry | Có hiệu lực khi filter/registry phù hợp kiểm tra, không global mặc định | Không | Không | Không |
| Xóa các session ở shared Spring Session store | Chặn session ID đã xóa ở các node dùng cùng store | Có, với index và consistency đúng | Không | Không | Không |
| Revoke refresh token tại AS | Không | Không | Có thể còn hiệu lực đến `exp` nếu offline JWT | Chặn refresh theo AS policy | Không nhất thiết |
| Revoke opaque access token tại AS | Không | Không | Không áp nếu API không introspect | Tùy grant | Không |
| Tăng account `securityVersion` | Chỉ khi verifier kiểm tra | Chỉ khi verifier kiểm tra | Chỉ khi token ràng buộc version/được đối chiếu | Chỉ khi AS kiểm tra | Không |
| RP-initiated/back-channel logout | Tùy tích hợp RP/IdP | Tùy tích hợp | Không tự động | Không tự động | Tùy hỗ trợ IdP |

Bảng biểu diễn **mặc định điển hình**, không phải bảo đảm tuyệt đối cho mọi deployment. Một AS có chính sách cascade revocation có thể thu hồi access token cùng grant; một app có filter đối chiếu account status mỗi request có thể chặn session sau lock. Hãy **đo hành vi thực tế** thay vì suy từ tên lệnh.

## 3. Chẩn đoán theo thứ tự: credential nào còn được chấp nhận?

Trước khi sửa code, dùng **hai phiên tách biệt** và một Bearer token test để tái hiện chính xác. Ghi timestamp UTC, account ID nội bộ, session reference đã hash, token `jti`/`sub` được pseudonymize, request ID, node ID, realm/tenant và kết quả. Không ghi raw cookie/Access Token vào log/ticket.

### Bước 1 — Xác định loại authentication thực sự được dùng

- **Cookie `JSESSIONID`/`SESSION`**: request được xác thực nhờ `HttpSession` và `SecurityContextRepository` hay cơ chế khác? Spring Session có thể thay tên cookie.
- **`Authorization: Bearer ...`**: resource server dùng `oauth2ResourceServer().jwt()` hay `opaqueToken()`? Một JWT có thể gửi tới introspection; nhìn hình dạng token chưa đủ xác định cơ chế.
- **Remember-me cookie**: sau logout session, browser có được đăng nhập lại bởi `RememberMeAuthenticationFilter` hay custom remember-me không?
- **SSO redirect**: người dùng bị logout ở RP nhưng lập tức đăng nhập lại vì IdP session vẫn active?
- **API key/client credentials**: có phải machine identity được cấp riêng, không phụ thuộc trạng thái account người dùng?
- **Một request concurrent đã qua authorization** trước thời điểm revoke: revoke không mặc định rollback response đang xử lý.

### Bước 2 — Quan sát đúng điểm tin cậy

| Câu hỏi | Bằng chứng cần lấy |
| --- | --- |
| Endpoint đã vào filter chain nào? | Matched `SecurityFilterChain`, matcher, SecurityFilterChain order |
| Principal được lấy từ đâu? | Session repository, JWT decoder, opaque introspector, custom filter |
| Có kiểm tra `account.status` trên request không? | AuthorizationManager/filter/service checks hoặc AS grant validation |
| Session hiện tại đã bị invalidate? | `HttpSession` còn tồn tại? Shared store có key session? |
| Các session khác có được tìm thấy? | Spring Session principal index, SessionRegistry hiện hành |
| Token còn hạn/đúng chữ ký? | `exp`, `iss`, `aud`, `kid`, signature validation result |
| Resource Server có revoke check? | `jti` denylist, securityVersion, account status, introspection active |
| Revoke có propagate sang AS/IdP? | API response, outbox status, retry, active check sau thao tác |
| Có cache tạo độ trễ không? | Redis/local cache TTL, JWT validator cache, introspection cache, replica lag |
| Có lỗi mạng/fail-open? | Circuit breaker behavior, 5xx/timeout và policy khi revoke store không sẵn sàng |

**Tránh sai lầm chẩn đoán:** không thể kết luận account chưa bị khóa chỉ vì token vẫn qua. Có thể **database đã locked đúng**, nhưng request không bao giờ đọc trạng thái đó. Ngược lại, request 401 không chứng minh mọi session đã bị xóa; có thể endpoint bị chặn bởi rule authorization khác.

### Bước 3 — Kiểm thử với môi trường an toàn

Dùng tài khoản và credential test, xác nhận trước revoke truy cập thành công; sau đó đánh dấu thời điểm commit của revoke và thử lại **cùng credential cũ** từ mỗi thiết bị/client. Không paste token/cookie thật vào issue tracker, browser console, shell history hay log có thể công khai. Phải kiểm tra cả **refresh sau revoke**, không chỉ gọi lại API bằng access token cũ.

Nếu mục tiêu SLO là thu hồi trong 5 giây, hãy đo khoảng từ **lệnh revoke đã commit** đến **mọi verifier liên quan từ chối**. Một cache 60 giây khiến lời hứa “thu hồi ngay” sai về mặt thực nghiệm.

## 4. Spring Security Servlet: logout chỉ ở đâu và tại sao phiên khác còn sống?

### 4.1. Logout chain mặc định xử lý gì?

Theo tài liệu Spring Security 6.5, khi ứng dụng dùng cấu hình logout mặc định, `POST /logout` với CSRF phù hợp đi qua `LogoutFilter` và các `LogoutHandler`:

- `SecurityContextLogoutHandler` invalidate **HTTP session của request hiện tại**, clear `SecurityContextHolder`/repository.
- Remember-me services được cấu hình phù hợp xử lý dọn remember-me của request.
- `CsrfLogoutHandler` dọn saved CSRF token; `LogoutSuccessEvent` có thể được phát.
- `LogoutSuccessHandler` xử lý response, mặc định thường redirect về `/login?logout`.

Trong cấu hình CSRF mặc định, `GET /logout` có thể là trang xác nhận, **không phải thao tác logout hoàn tất**; cần POST hợp lệ. Browser xoá cookie bằng JavaScript nhưng session server vẫn sống nếu chưa revoke. Ngược lại, invalidate session ở server khiến cookie cũ vô giá trị cho session đó ngay cả khi cookie vẫn nằm ở client.

~~~text
Browser A -- POST /logout + CSRF -->
    LogoutFilter
      -> SecurityContextLogoutHandler
           HttpSession A.invalidate()
           clear SecurityContext
      -> remember-me / CSRF cleanup
      -> redirect/204

Browser B giữ HttpSession B -- KHÔNG bị hành động trên xóa mặc định -->
    Request authenticated bằng session B vẫn có thể tiếp tục.
~~~

Nếu app tự tạo `@PostMapping("/logout")` rồi chỉ trả 200, có thể đã **bỏ qua** `LogoutFilter` hoặc không gọi đúng `SecurityContextLogoutHandler`. Tài liệu Spring khuyên ưu tiên logout DSL; custom endpoint phải thực hiện cleanup đầy đủ và đảm bảo route/CSRF chính xác.

### 4.2. Các nguyên nhân chẩn đoán rất thường gặp

1. Logout đường `GET` không thực thi do CSRF. Kiểm tra method/status/server log, không đo bằng “UI đã chuyển trang”.
2. Frontend chỉ xóa state Redux/localStorage, nhưng session server hoặc refresh token vẫn còn.
3. Cookie `JSESSIONID` trên browser B là **session khác**, logout A không tác động.
4. App triển khai nhiều `SecurityFilterChain`, endpoint logout nằm ở chain khác hoặc chain matcher không phù hợp.
5. Có **remember-me** hoặc SSO redirect tự cấp phiên mới, khiến user tưởng session cũ sống lại.
6. Session registry lưu in-memory từng node; revoke ở node A không biết session trên node B.
7. Index principal bằng username/email không ổn định/tenant không tách; lookup trả thiếu hoặc sai.
8. Dùng `SessionRegistry.expireNow()` nhưng không có cơ chế nhận diện expired sessions tại request sau; tưởng đánh dấu tương đương delete vật lý.
9. App dùng Spring Session nhưng chỉ invalidate `HttpSession` của current request, chưa xóa các session khác trong repository.
10. Custom authentication filter tự tạo lại `SecurityContext` từ token/remember-me, độc lập session bị xóa.
11. Admin đổi flag `account.locked` trong DB, nhưng các session đã lưu Authentication không check lại account state.
12. Cache trạng thái account, user roles hoặc session index chưa invalidated.

### 4.3. SessionRegistry không phải kho session phân tán mặc định

`SessionRegistry` quản lý thông tin sessions được đăng ký trong một Spring Security app. `SessionInformation.expireNow()` đánh dấu expired; cơ chế concurrent-session filter và session management phù hợp có thể từ chối khi session đó gửi request tiếp. **Không xem đó là lệnh hủy ngay mọi session trên mọi node** nếu SessionRegistry là bản `SessionRegistryImpl` trong memory từng JVM.

~~~java
// Snippet minh họa; yêu cầu có SessionRegistry/session config phù hợp.
// Không phải class Java độc lập.
for (SessionInformation info :
        sessionRegistry.getAllSessions(principal, false)) {
    info.expireNow();
}
~~~

Để dùng đoạn này trong project, `SessionInformation` nằm ở `org.springframework.security.core.session.SessionInformation` và `SessionRegistry` ở `org.springframework.security.core.session.SessionRegistry`. Principal cần có `equals()/hashCode()` ổn định khi sử dụng `SessionRegistryImpl`, hoặc registry có thể không tìm đúng session. Sau `expireNow()` phải test request thật với session cũ và filter; đừng chỉ assert flag đã bật.

Nếu chọn **session store chia sẻ** như Spring Session Redis/JDBC, có thể xóa session server-side theo ID thông qua repository có chỉ mục. Cần xác minh tất cả nodes dùng **cùng namespace/config/cluster** và index chứa local principal ổn định. Spring Session không mặc nhiên biết mọi cách xác thực tùy biến; có trường hợp index không được populate nếu custom security flow.

## 5. Spring Session: xóa đúng các phiên thuộc user

### 5.1. Nguyên tắc

Spring Session cung cấp `FindByIndexNameSessionRepository<S extends Session>` và `findByPrincipalName(principalName)` để liệt kê session có chỉ mục `PRINCIPAL_NAME_INDEX_NAME`. `deleteById(sessionId)` xóa session theo ID trong repository tương ứng. Các API này thực sự tồn tại ở Spring Session 3.5.x. **Chúng chỉ áp dụng cho session trong kho đã được index**, không nhìn thấy Bearer JWT, refresh token, IdP session hay session ở storage khác.

**Chỉ mục có thể thiếu**: trong hệ thống tùy biến, cần đảm bảo `PRINCIPAL_NAME_INDEX_NAME` được ghi đúng. Một vài implementation có resolver đọc Spring Security context để xây index. Tùy phiên bản/driver, tìm session theo principal có thể có hạn chế consistency/indexing; cần xác minh bằng integration test và monitoring.

### 5.2. Mã Java dùng trong Spring project

File `src/main/java/example/SessionRevocationService.java` (cần dependency Spring Session và nơi khác inject repository phù hợp; class chỉ biểu diễn thao tác session):

~~~java
package example;

import java.util.Map;
import java.util.Objects;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

public final class SessionRevocationService {

    private SessionRevocationService() { }

    public static <S extends Session> int revokeIndexedSessions(
            FindByIndexNameSessionRepository<S> repository,
            String principalName) {

        Objects.requireNonNull(repository, "repository");
        Objects.requireNonNull(principalName, "principalName");
        if (principalName.isBlank()) {
            throw new IllegalArgumentException("blank principal");
        }

        Map<String, S> found =
            repository.findByPrincipalName(principalName);

        for (String sessionId : found.keySet()) {
            repository.deleteById(sessionId);
        }
        return found.size();
    }
}
~~~

Đoạn này hợp lệ về mặt Java generics nhưng chỉ là **hàm chức năng** cho một repository đã cấu hình. Nó **không bảo đảm atomic global revoke**, vì một login/session mới có thể được tạo giữa lúc enumerate và delete. Trong incident nghi takeover, kết hợp **account security version / account state check** tại các điểm tạo/tiếp nhận session, và phối hợp database transaction/outbox/locking phù hợp.

**Cảnh báo kiến trúc:** principal name cần là **local user ID bền vững và đúng tenant**. Nếu `Principal.getName()` chỉ là email hay username được đổi, session index có thể lệch với `userId`. Đừng truyền tên user do browser nhập để xóa session người khác; lệnh admin revoke phải có authorization/approval và audit.

### 5.3. Kiểm tra hậu quả thay vì chỉ kiểm tra return value

~~~text
Given:
  - User u-123 có session S1 (browser A) và S2 (browser B).
  - Spring Session repository index thấy đúng S1, S2.
When:
  - Admin khóa u-123 và chạy revokeIndexedSessions(...).
Then:
  - findById(S1) và findById(S2) không thấy session hợp lệ.
  - GET protected route bằng cookie cũ trên browser A/B bị 401 hoặc redirect login.
  - Không có remember-me/SSO silently re-login trong test này.
  - User khác u-999 vẫn đăng nhập được.
~~~

Nếu số session tìm thấy bằng 0 trong khi browser B đang authenticated, cần kiểm tra **principal index**, repository instance, session namespace, serializer, Redis/JDBC dữ liệu, deployment region, session TTL và custom authentication. Không kết luận “không có active sessions” chỉ từ map rỗng.

### 5.4. Nhiều region và cache

- Spring Session repository là điểm nhất quán cho session dùng chung, nhưng ứng dụng có thể có nhiều region/store hoặc L1 cache khác nhau.
- Các session ID mới được tạo **sau** khi enumerate/delete không bị ảnh hưởng nếu account vẫn cho phép login. Cần khóa ở **điểm phát phiên** và kiểm tra account state.
- Thiết bị offline giữ cookie cũ; khi online thì server phải từ chối, không cần có cách xóa cookie trên thiết bị đó.
- Session deletion và DB lock của app không tự có một transaction phân tán; dùng policy rõ để xử lý một phần lỗi, retry có idempotency và verify hậu kiểm.

## 6. Khóa account vẫn không chặn JWT: lỗi ở đâu?

### 6.1. JWT là credential đã được phát hành

Một JWT access token chuẩn mang `iss`, `sub`, `aud`, `exp`, `iat`, có thể `jti` và scope/roles. Resource Server xác thực chữ ký và validators trên các claims. Nếu verifier **không kiểm tra account status/revocation** thì:

~~~text
t0: User ACTIVE, AS phát JWT T (exp = t0 + 15 phút)
t1: Admin đặt user LOCKED tại app DB
t2: Client gọi API bằng JWT T
t3: Resource Server chỉ verify signature/iss/aud/exp => token vẫn hợp lệ
t4: JWT T hết hạn => Resource Server bắt đầu từ chối vì exp
~~~

Token vẫn có thể bị từ chối sớm hơn bởi các biện pháp bổ sung, nhưng **đổi password, đặt account locked hoặc xóa HTTP session không thay đổi chữ ký** của JWT T. `JwtDecoder` cũng không mặc nhiên gọi `UserDetailsService` theo `sub` mỗi lần.

### 6.2. Kiểm tra đúng nơi

- Resource Server có `.oauth2ResourceServer(oauth -> oauth.jwt(...))` thực sự ở chain của API này không?
- Decoder đang validate đúng issuer, audience, expiry/nbf, key và algorithm allowlist?
- Sau decoder, app có policy `account.active/securityVersion/tokenFamily` hay không? Check đang chạy **trước authorization** trên mọi endpoint nhạy cảm chứ không chỉ một controller?
- Token `sub` là local ID hay IdP subject? Có mapping identity đáng tin và ràng buộc tenant trước khi kiểm tra account local?
- Cache account state có TTL bao nhiêu? Node B đã refresh cache sau khi lock chưa?
- Có endpoint hoặc WebSocket/SSE connection sống lâu **không áp revocation check** trong stream?
- API nào dùng opaque introspection, API nào chỉ JWT offline? Chính sách khác nhau có thể tạo “revoke một nửa”.

### 6.3. Ba hướng kiểm soát access JWT

| Biện pháp | Cách hoạt động | Tradeoff |
| --- | --- | --- |
| **Short TTL** | Token hết hạn nhanh, refresh token bị chặn khi lock | Còn residual window đến `exp`; không phải immediate revoke |
| **Denylist `jti`/token family** | Mỗi request kiểm tra token identifier ở shared revocation store | Lookup latency, storage/TTL, consistency, fail policy |
| **Security version / account-state check** | Token ràng buộc `userId` + `version` lúc cấp, mọi verifier đối chiếu version/current state | Cần online/shared state; token IdP ngoài có thể không mang claim đó |

Một chiến lược khác là **opaque token + introspection**: Resource Server hỏi AS về `active`, đổi lấy latency/availability; cache introspection vẫn tạo cửa sổ nếu TTL lớn. Không nhất thiết chọn chỉ một cơ chế; áp nhiều mức theo rủi ro và giới hạn latency.

**Nếu dùng denylist:** không log raw token. `jti` phải unique và được ràng buộc với issuer/audience; TTL bản ghi revoke không ngắn hơn lifetime còn lại mà token có thể được chấp nhận. Nếu dùng account version, phải đảm bảo **tất cả** Resource Servers và batch consumers kiểm tra, không chỉ gateway. Chặn stale cache và fail-open vô thức ở endpoint high-risk.

### 6.4. Account status sau lock và phiên còn sống

Một `UserDetails` từng được load lúc login và lưu trong session có thể thể hiện trạng thái cũ; cập nhật database sau đó **không làm object trong SecurityContext tự thay đổi**. Muốn khóa account được áp ngay, cần một trong các cơ chế:

- Đăng xuất/xóa các sessions đã biết qua shared session repository, **kết hợp chặn tạo session mới**.
- Mỗi request/endpoint nhạy cảm kiểm tra account status và security version bằng trusted service/store.
- Dùng session security-version mang lúc phát session, version tăng khi lock/unlock/recovery và so sánh trước khi cấp quyền.
- Với WebSocket/long-lived connection, có chính sách đóng connection hoặc kiểm tra lại định kỳ theo risk budget.

**Không dựa duy nhất vào `UserDetails.isAccountNonLocked()` khi authentication ban đầu** nếu yêu cầu khóa có hiệu lực trên session đã được cấp trước đó. Lúc đầu check ấy hữu ích, nhưng session cũ không tự re-auth mỗi request.

## 7. Refresh token, OAuth revoke, opaque token và IdP session

### 7.1. Refresh token sống ở Authorization Server

Resource Server thường **không** quản lý refresh token và **không** phát refresh token mới. Nếu login với OAuth2/OIDC, refresh token có thể được lưu ở Authorization Server, OAuth client hoặc token store riêng. Một backend chỉ xóa local session mà không báo AS revoke grant thì thiết bị khác có thể tiếp tục gọi token endpoint để lấy access token.

Cần kiểm tra:

1. Client/grant ID và refresh-token family của user liên quan được quản lý ở đâu?
2. AS có kiểm tra account disabled/locked trước khi refresh không? Đã thử bằng refresh token cũ chưa?
3. Refresh-token rotation có phát hiện **reuse** và revoke family theo policy không?
4. Race: refresh bắt đầu **ngay trước** lock/revoke có thể cấp token mới **sau** commit nếu AS không chặn concurrent issuance.
5. Lệnh revoke trả thành công có chắc đã có hiệu lực ở tất cả verifier/token stores chưa? Có retry/queue/replica lag không?

### 7.2. RFC 7009 và lời hứa “thu hồi hết”

RFC 7009 đưa ra **token revocation endpoint**; RFC khuyến khích Authorization Server xử lý revoke liên quan grant. Nhưng việc **revoke refresh token không bảo đảm mọi JWT access token đã cấp bị từ chối ngay** nếu Resource Server verify offline, không dùng denylist/status check.

Ở client, xóa `OAuth2AuthorizedClient` chỉ xóa thông tin token **client lưu**; có thể ngăn client này gọi API tiếp sau khi mất token, nhưng không phải một lời gọi revoke token tại AS. Ngược lại, AS revoke refresh/access grant không tự invalidate mọi HTTP session hiện tại trong app.

Không gửi raw token vào incident logs; revocation endpoint chỉ được gọi qua HTTPS và phương thức client authentication thích hợp. Request lặp cần idempotency. Một HTTP 200 từ revocation endpoint **không đủ** để chứng minh các access JWT đã bị chặn ở API offline.

### 7.3. Opaque token introspection

Với opaque token, Resource Server có thể gửi token đến `OpaqueTokenIntrospector`; AS trả `active=true` hoặc `false`. Lúc khóa account, AS phải cập nhật trạng thái grant/token, sau đó Resource Server phải **hỏi lại** hoặc dùng cache có TTL phù hợp. Nếu cache `active=true` trong 10 phút, revoke chỉ có hiệu lực chắc chắn khi cache đó hết hạn hoặc invalidated.

Triệu chứng:

~~~text
t0: Resource Server introspect opaque token => active=true
t1: Response cached TTL=300s
t2: Authorization Server revoke => active=false
t3: Resource Server vẫn accept cached active=true
t4: TTL hết hạn / cache invalidated, introspect lại => active=false
~~~

Kiểm tra hệ thống có `OpaqueTokenIntrospector` thật không hay test/staging đã mock nó để luôn trả principal. **Không coi `opaqueToken()` hoặc `mockOpaqueToken()` của Spring Security Test là bằng chứng introspection HTTP đã chạy**.

### 7.4. Identity Provider session và SSO silent login

Với OIDC `oauth2Login()`, app có **Relying Party session**, IdP có **OP/SSO session**. Logout RP không đương nhiên logout IdP. Người dùng bấm logout xong lại bấm Login with Provider và được đăng nhập ngay: có thể đó là **phiên RP mới hợp lệ được tạo bằng IdP SSO vẫn active**, chứ không phải cookie cũ chưa xóa.

Nếu cần phối hợp logout, nghiên cứu RP-initiated logout/back-channel logout/front-channel logout theo khả năng IdP, chính sách assurance và sự kiện disable ở IdP. Không trộn `logoutSuccessHandler` của RP với việc revoke OAuth grant; các thao tác tách biệt. Với IdP ngoài không hỗ trợ hoặc fail, ghi tình trạng `PENDING_EXTERNAL_LOGOUT/REVOKE` và xử lý có giới hạn.

### 7.5. Remember-me: kênh tạo lại phiên bị bỏ sót

Nếu ứng dụng dùng persistent remember-me token, browser có thể được tạo Authentication mới khi cookie/session chính hết hạn. Logout mặc định của Spring có các handler cho remember-me khi được cấu hình, nhưng **logout một thiết bị không nhất thiết xóa persistent token của mọi thiết bị**. Trong sự cố compromise, kiểm tra kho persistent tokens/series hoặc tự thiết kế remembered-device grant theo user để có thể revoke toàn bộ. Đừng tự nhận “mọi session đã chết” khi browser có thể tự login lại bằng remember-me hoặc IdP SSO.

## 8. Quy trình sửa triệt để: transaction, propagation và bảo đảm kiểm chứng

### 8.1. Quy trình thu hồi nhiều loại credential

~~~text
Authorized operator / verified account owner requests REVOKE_ALL
    |
    v
Check authorization, step-up, incident ID, scope
    |
    v
DB transaction:
   lock account row; mark LOCKED (if policy)
   increment securityVersion once per incident
   mark known session/refresh grants revoked
   write incident + outbox events
   commit
    |
    v
Asynchronous workers (idempotent):
   delete indexed Spring Sessions
   invalidate other local sessions/remember-me tokens
   call Authorization Server token-family/grant revoke
   call IdP logout/revoke APIs if supported
   broadcast cache invalidation / denylist update
    |
    v
All authenticators/verifiers:
   reject old securityVersion, old session/grant, revoked jti
   reject new authentication if account LOCKED
    |
    v
Re-test from every device/API/node/region
    |
    +-- all effective -> CONFIRMED
    +-- some pending -> PARTIAL / PENDING_EXTERNAL + alert
~~~

**DB transaction không thể bao phủ atomic nhiều remote IdP/AS**, nên cần outbox, retries có idempotency, dead-letter handling, trạng thái partial, deadline và audit. Không báo “đã thu hồi mọi thứ” nếu token từ một IdP chưa có xác nhận. Khi lock account phải chặn **issue session/token mới** trong cùng cơ chế kiểm tra trạng thái, nếu không có race tạo session ngay sau enumerate/delete.

### 8.2. Race nguy hiểm: lock rồi refresh song song

~~~text
Request A: refresh token -> đọc account ACTIVE
Admin B:   lock account -> commit LOCKED + version=13
Request A: ký access token mới (version=12 hoặc không version)
Resource Server: token có signature/exp hợp lệ -> ACCEPT!
~~~

Giải pháp: enforce account status/version gần hoặc **trong transaction phát token** ở AS, sử dụng lock/CAS/version policy; resource servers đối chiếu `version`/revocation state theo nơi tin cậy. Nếu token phát từ IdP khác không thể thêm local version, dùng local denylist/check hoặc token lifetime budget. Kiểm tra concurrent test bằng barrier, không chỉ unit test tuần tự.

### 8.3. Cảnh báo cache và multi-region

- Một node cache account status 5 phút sẽ còn cho phép phiên cũ dù DB đã LOCKED.
- Redis session store ở khu vực A nhưng server B trỏ sang Redis namespace khác sẽ không bị xóa.
- JWT offline trên Resource Server C không có revoke check thì vẫn chấp nhận token; một gateway check thôi không chặn đường đi tắt.
- Invalidation event bus có thể mất event hoặc đến không đúng thứ tự; phiên mới được cấp sau recovery không được bị stale revoke event xóa.
- Persistent connection (WebSocket/SSE) không tự đóng vì database thay đổi, phải có policy re-evaluate/close.
- Với endpoint high-risk, không được im lặng **fail open** khi revocation store outage nếu security guarantee đòi tức thời.

### 8.4. Thiết kế bằng chứng sau sửa

Thay vì “đã gọi hàm revoke”, mỗi incident lưu: action ID, account ref, thời điểm commit, loại credential bị ảnh hưởng, trạng thái từng store/AS/IdP, số sessions tìm thấy/xóa, số retry, node/region đã xác minh, các request thử lại bằng credential cũ và thời gian tới rejection. Thông tin phải bảo vệ khỏi PII/secret leakage và chỉ accessible theo role.

**Không xóa log/audit chứng cứ** để “làm sạch” sau sự cố; có retention, integrity và quyền xem riêng. Không đưa raw token, cookie, OTP hoặc session ID vào telemetry công khai.

## 9. Java 17 chạy độc lập: mô phỏng vì sao khóa account không giết JWT offline

Mã sau chạy bằng **Java 17 thuần**, không cần Spring. Nó mô phỏng cùng một user có session, refresh grant và JWT đã phát. Khi lock account, session và refresh grant bị xóa, version tăng; **kiểm tra JWT offline chỉ dựa expiry** vẫn cho phép JWT đến hạn, trong khi **kiểm tra account version/status bổ sung** từ chối. Điều này minh họa ranh giới trust; **không** có JWS signature/decoder thật, không có network, cache hay database, nên **không dùng làm security implementation production**.

Tạo file `RevocationDiagnosisDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class RevocationDiagnosisDemo {

    record Token(String userId, long issuedVersion,
                 long expiresAtEpochSeconds) {
    }

    private static final long NOW = 1_700_000_000L;

    private final Map<String, Long> versions = new HashMap<>();
    private final Map<String, Boolean> locked = new HashMap<>();
    private final Map<String, Token> sessions = new HashMap<>();
    private final Map<String, Token> refreshGrants = new HashMap<>();

    private long version(String userId) {
        return versions.getOrDefault(userId, 0L);
    }

    private boolean isLocked(String userId) {
        return locked.getOrDefault(userId, false);
    }

    synchronized Token issueAccess(String userId) {
        Objects.requireNonNull(userId);
        if (isLocked(userId)) {
            throw new IllegalStateException("locked");
        }
        return new Token(userId, version(userId), NOW + 900);
    }

    synchronized void issueSession(String userId, String id) {
        Objects.requireNonNull(id);
        Token issued = issueAccess(userId);
        sessions.put(id, issued);
    }

    synchronized void issueRefresh(String userId, String id) {
        Objects.requireNonNull(id);
        Token issued = issueAccess(userId);
        refreshGrants.put(id, issued);
    }

    synchronized boolean sessionValid(String id) {
        Token token = sessions.get(id);
        return token != null
            && !isLocked(token.userId())
            && token.issuedVersion() == version(token.userId());
    }

    synchronized boolean refreshValid(String id) {
        Token token = refreshGrants.get(id);
        return token != null
            && !isLocked(token.userId())
            && token.issuedVersion() == version(token.userId());
    }

    // Mô phỏng decoder chỉ check expiry; KHÔNG verify signature.
    static boolean offlineExpiryOnly(Token token) {
        return token.expiresAtEpochSeconds() > NOW;
    }

    synchronized boolean withAccountVersion(Token token) {
        return offlineExpiryOnly(token)
            && !isLocked(token.userId())
            && token.issuedVersion() == version(token.userId());
    }

    synchronized void lockAndRevoke(String userId) {
        Objects.requireNonNull(userId);
        locked.put(userId, true);
        versions.put(userId, version(userId) + 1);
        sessions.entrySet().removeIf(
            entry -> entry.getValue().userId().equals(userId));
        refreshGrants.entrySet().removeIf(
            entry -> entry.getValue().userId().equals(userId));
    }

    synchronized void unlockAfterVerifiedRecovery(String userId) {
        Objects.requireNonNull(userId);
        locked.put(userId, false);
        // KHÔNG giảm version về 0; token cũ vẫn bị chặn.
    }

    public static void main(String[] args) {
        RevocationDiagnosisDemo store = new RevocationDiagnosisDemo();
        store.issueSession("alice", "session-old");
        store.issueRefresh("alice", "refresh-old");
        Token jwtOld = store.issueAccess("alice");

        System.out.println("before.session="
            + store.sessionValid("session-old"));
        System.out.println("before.refresh="
            + store.refreshValid("refresh-old"));
        System.out.println("before.offlineJwt="
            + offlineExpiryOnly(jwtOld));
        System.out.println("before.checkedJwt="
            + store.withAccountVersion(jwtOld));

        store.lockAndRevoke("alice");

        System.out.println("after.session="
            + store.sessionValid("session-old"));
        System.out.println("after.refresh="
            + store.refreshValid("refresh-old"));
        System.out.println("after.offlineJwt="
            + offlineExpiryOnly(jwtOld));
        System.out.println("after.checkedJwt="
            + store.withAccountVersion(jwtOld));

        store.unlockAfterVerifiedRecovery("alice");
        System.out.println("recovered.oldCheckedJwt="
            + store.withAccountVersion(jwtOld));
        store.issueSession("alice", "session-new");
        System.out.println("recovered.newSession="
            + store.sessionValid("session-new"));
    }
}
~~~

Chạy:

~~~bash
javac RevocationDiagnosisDemo.java
java RevocationDiagnosisDemo
~~~

**Stdout chính xác** theo mô hình (clock cố định, không random):

~~~text
before.session=true
before.refresh=true
before.offlineJwt=true
before.checkedJwt=true
after.session=false
after.refresh=false
after.offlineJwt=true
after.checkedJwt=false
recovered.oldCheckedJwt=false
recovered.newSession=true
~~~

**Ý nghĩa:** dòng `after.offlineJwt=true` là điều đáng chẩn đoán: một access token từng được cấp có thể còn được chấp nhận bởi verifier **không hỏi lại account trạng thái**. Dòng `after.checkedJwt=false` chứng minh bổ sung trạng thái từ chối token cũ, chứ không nói Spring tự làm vậy. Unlock sau xác minh **không hồi sinh JWT cũ** vì version đã tăng. Việc cho phép cấp session mới trong demo chỉ là thao tác mô phỏng: production phải xác thực lại/step-up đủ assurance, không có endpoint `unlockAfterVerifiedRecovery` vô kiểm soát.

**Các giới hạn:** `NOW` cố định để tạo stdout ổn định, RSA/JWT không thực sự được kiểm tra; `Map` và `synchronized` chỉ hoạt động trong một JVM. Không đưa `id` của session/token thật vào log hoặc dùng Map in-memory này thay Redis/DB/Authorization Server trong production.

### 9.1. JUnit Jupiter: kiểm tra bất biến quan trọng

Nếu đã có JUnit 5, đặt `RevocationDiagnosisDemoTest.java` cùng package với demo (mã mặc định không khai báo `package` thì file test cũng không khai báo):

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RevocationDiagnosisDemoTest {

    @Test
    void revokedSessionAndRefreshAreRejected() {
        var store = new RevocationDiagnosisDemo();
        store.issueSession("alice", "s1");
        store.issueRefresh("alice", "r1");

        assertTrue(store.sessionValid("s1"));
        assertTrue(store.refreshValid("r1"));
        store.lockAndRevoke("alice");
        assertFalse(store.sessionValid("s1"));
        assertFalse(store.refreshValid("r1"));
    }

    @Test
    void offlineTokenMaySurviveWhileVersionCheckBlocksIt() {
        var store = new RevocationDiagnosisDemo();
        var issued = store.issueAccess("alice");
        store.lockAndRevoke("alice");

        assertTrue(RevocationDiagnosisDemo.offlineExpiryOnly(issued));
        assertFalse(store.withAccountVersion(issued));
    }

    @Test
    void unlockDoesNotResurrectOldAccessToken() {
        var store = new RevocationDiagnosisDemo();
        var issued = store.issueAccess("alice");
        store.lockAndRevoke("alice");
        store.unlockAfterVerifiedRecovery("alice");

        assertFalse(store.withAccountVersion(issued));
    }

    @Test
    void accountLockDoesNotRevokeOtherUserSessions() {
        var store = new RevocationDiagnosisDemo();
        store.issueSession("alice", "s-a");
        store.issueSession("bob", "s-b");

        store.lockAndRevoke("alice");
        assertFalse(store.sessionValid("s-a"));
        assertTrue(store.sessionValid("s-b"));
    }

    @Test
    void lockedAccountCannotIssueNewAccessToken() {
        var store = new RevocationDiagnosisDemo();
        store.lockAndRevoke("alice");
        assertThrows(IllegalStateException.class,
            () -> store.issueAccess("alice"));
    }
}
~~~

Các test này chỉ kiểm tra **domain simulation**. Cần test integration với Spring Session store, Resource Server JWT decoder, AS refresh endpoint, Opaque introspection và các client thực sự gửi credential cũ. Đừng viết test dùng `jwt()`/`mockJwt()` rồi kết luận đã kiểm chứng denylist/chữ ký/refresh revocation: các công cụ này có thể inject Authentication giả và bỏ qua đường decoder.

## 10. Ma trận kiểm thử HTTP/integration để tìm lỗi thật

### Hai phiên và token phải hoàn toàn độc lập

~~~text
PRECONDITION:
  User alice ACTIVE.
  Device A login -> cookie S1.
  Device B login -> cookie S2.
  OAuth client obtains access token T1 + refresh token R1.

ACTION:
  Admin locks alice (with authorization and audit).
  Revocation policy executes.

ASSERT:
  GET /private with cookie S1 -> unauthenticated/denied.
  GET /private with cookie S2 -> unauthenticated/denied.
  GET /private with Bearer T1 -> 401/403 as designed by revocation policy.
  POST token refresh using R1 -> token endpoint rejects.
  A login using old credential while LOCKED -> rejected.
  Account bob's valid session remains accepted.
  Repeat on every node/region and after caches warm.
~~~

Khi resource server dùng JWT offline với TTL hữu hạn và **không có immediate revocation guarantee**, test phải phản ánh chính xác contract: T1 có thể còn dùng đến `exp`, nhưng hệ thống phải kiểm soát endpoint high-risk hoặc chấp nhận residual risk đã ký duyệt. Không viết assertion 401 rồi coi test đã chứng minh nếu policy thực cho phép “residual 15 phút”.

### Ma trận triệu chứng → nguyên nhân → hướng kiểm tra

| Triệu chứng | Khả năng cao | Phép kiểm chứng |
| --- | --- | --- |
| Logout UI chuyển login nhưng cookie cũ vẫn gọi được API | Request không chạy logout filter, controller tự redirect, hoặc API dùng Bearer khác | Trace matcher/LogoutFilter, test POST với CSRF, kiểm tra nguồn auth |
| Browser A logout, browser B vẫn vào được | Local logout chỉ invalidate S1 | So sánh session ID refs và shared store |
| `SessionRegistry.expireNow()` rồi session vẫn hoạt động | Expiration marking không được filter xử lý, registry sai node/principal | Kiểm tra registry, filter chain, session request sau expire |
| `findByPrincipalName` trả map trống | Index thiếu/sai local ID/tenant/store namespace | Kiểm tra Spring Session index, repository config |
| User LOCKED nhưng request session cũ OK | Không re-evaluate account status/security version | Bật guard ở protected paths, xóa indexed sessions |
| JWT còn chạy sau đổi password | Offline JWT signature/time vẫn valid | Kiểm tra decoder vs denylist/version và TTL |
| JWT bị chặn ở gateway nhưng API nội bộ vẫn chấp nhận | Service bypass gateway hoặc validator config lệch | Test direct service path/mTLS/authz policies |
| Refresh token cũ vẫn đổi token mới | AS chưa revoke family hoặc không check account lock | Test token endpoint, grant store/issuer |
| Opaque token active sau revoke | AS chưa cập nhật active hoặc introspection cache còn giữ true | Introspect lại từ client sạch, đo TTL |
| SSO tự đăng nhập lại sau logout | OP session còn, tạo RP session mới | Kiểm tra session ID mới và OIDC authorization flow |
| Remember-me tái tạo login | Persistent remember-me grant chưa revoke | Xóa/đánh dấu series/device, test cookie cũ |
| Node A từ chối, node B đồng ý | Session/revocation/cache stores chưa đồng bộ | Test load balancer pin node, namespace, consistency |
| 401 lúc đầu nhưng sau vài giây lại 200 | Refresh/re-login race hoặc cached principal | Correlate token issue time, session new ID và event |
| Revoke API 200 nhưng AS chưa hoàn tất | Async outbox pending, partial failure | Trạng thái per-provider và retry/audit |
| WebSocket vẫn stream sau lock | Long-lived connection không kiểm tra lại auth | Test close/revalidate on account lock |
| Vẫn 200 với `MockMvc.with(jwt())` | Test đã inject Authentication giả, không đi qua decoder | Gửi raw Bearer JWT/real client trong test |

### Checklist test chất lượng

- Không chỉ kiểm tra DB flag `LOCKED`; assert HTTP với **old credential** sau commit.
- Test từ các node/region/gateway đường đi hợp pháp khác nhau.
- Assert tài khoản khác và session mới sau recovery có policy đúng, không bị xóa nhầm.
- Test refresh/revoke race, login/revoke race và delayed outbox deliveries.
- Đo `revocation_lag_p95/p99` theo từng loại credential và phương thức xác thực.
- Kiểm tra Bearer `WWW-Authenticate`/HTTP status cho invalid token, và không tiết lộ lý do nội bộ trong response.
- Mọi test credential dùng account test riêng, token giả/sinh trong môi trường test, không copy raw token trong CI logs.
- Với Spring Security Test, phân biệt test authorization bằng principal giả với **decoder/introspection thật**.
- Kiểm tra khi Redis/DB/AS down: endpoint nhạy cảm nên fail closed theo threat model.
- Nếu policy cho residual JWT lifetime, kiểm tra hạn tối đa và thông báo vận hành, đừng gọi là immediate revoke.

## 11. Runbook chẩn đoán nhanh cho on-call

### Nhận incident

1. **Phân loại**: User bị LOCKED hay đã logout? Logout trên một hay mọi thiết bị? Token JWT, opaque, refresh hay cookie session? Đừng nói “token” chung chung.
2. **Thu thập an toàn**: account ID, incident ID, request ID, thời gian UTC, issuer/audience, fingerprint/jti reference đã pseudonymize; **không** thu raw secrets.
3. **Tái hiện**: dùng account test và hai client độc lập; xác minh trước revoke có quyền truy cập; chụp HTTP status sau.
4. **Đi theo filter chain**: endpoint match chain nào, auth source nào, principal mapping/tenant nào, có account state guard hay không?
5. **Kiểm kho trạng thái**: shared Spring Session/registry/remember-me, Refresh family và AS, JWT denylist/version, opaque introspection, SSO session và caches.
6. **Tìm propagation gap**: outbox pending, queue retry, node khác, Redis namespace khác, AS/IdP API lỗi, cache TTL hoặc refresh race.
7. **Contain ngay theo policy**: chặn endpoint high-risk/issue refresh, revoke family/sessions, tăng version, giới hạn account, audit. Không tự xóa tất cả dữ liệu để “fix”.
8. **Kiểm chứng hậu xử lý**: old credential trên từng verifier phải bị từ chối hoặc residual lifetime đúng SLA; ghi phần nào còn pending.
9. **Khôi phục an toàn**: người dùng xác minh danh tính/step-up, rotate credential nghi bị lộ, đăng ký lại factor nếu cần; không hồi sinh session/token cũ sau unlock.
10. **Hậu kiểm**: cập nhật runbook, test CI multi-node, monitor lag và yêu cầu mã hóa trạng thái partial.

### Những thước đo nên có

- `time_to_detect`, `time_to_contain`, `revocation_lag` theo session/JWT/refresh/opaque.
- Số active sessions tìm thấy và số xóa thành công; số session index misses.
- Số JWT cũ còn pass sau lock trong khoảng thời gian cho phép.
- Refresh reuse và số lần AS từ chối/nhận cấp token sau revoke.
- `introspection_cache_ttl`, số cache invalidation misses, số lần fail-open.
- Outbox backlog, số external revoke chờ xác nhận và retry count.
- Các verifier/node/region chưa có tính năng revoke guard.
- Số case “relogin vì SSO/remember-me” bị nhầm thành “session chưa xóa”.

Không dùng email/raw token làm nhãn metrics có cardinality cao; đặt forensic context trong logs có phân quyền và retention.

## 12. Những lỗi sửa sai thường gặp

1. **Chỉ đổi `enabled=false`/`locked=true` trong database rồi tưởng mọi phiên chết**: session/JWT không tự check lại.
2. **Chỉ xóa `SecurityContextHolder`**: context trong thread/request hiện tại không xóa session ở thiết bị khác.
3. **Chỉ gọi `HttpSession.invalidate()` một lần**: chỉ current session, không phải global logout.
4. **Dùng `SessionRegistryImpl` cục bộ** cho app nhiều node rồi kết luận “đã logout tất cả”.
5. **Tưởng `SessionInformation.expireNow()` xóa ngay trong repository**: chỉ đánh dấu và cần cơ chế kiểm tra/cleanup.
6. **Tin `findByPrincipalName` trả rỗng nghĩa không còn session**: index có thể thiếu hoặc namespace sai.
7. **Xóa cookie client nhưng vẫn giữ remember-me/refresh token**, cho phép tự động tái xác thực.
8. **Khóa user nhưng AS vẫn phát refresh token mới** vì không kiểm tra account status/authorization grant.
9. **Revoke refresh token rồi báo access JWT chết ngay** dù Resource Server verify offline.
10. **Bỏ qua `aud`/`iss` trong validator** và xử lý lock sai tenant/issuer, tạo lỗi security khác.
11. **Denylist lưu ít hơn TTL còn lại của JWT**: token đã revoke sống lại khi record hết hạn.
12. **Chỉ kiểm tra securityVersion ở gateway**: có service nội bộ bypass gateway.
13. **Cache account status quá lâu hoặc fail open** khi revoke store không sẵn sàng.
14. **Gọi logout IdP rồi tin app session mất**: SSO IdP và RP session độc lập.
15. **Thấy browser tự login lại rồi kết luận logout handler không chạy**: có thể tạo session mới từ remember-me/SSO.
16. **Không có test concurrent revoke/refresh**: vẫn phát token mới ở thời điểm cửa sổ race.
17. **Đưa token/cookie thật vào ticket** để debug: gây lộ credential đang sống.
18. **Chỉ assert `status=401` trong MockMvc có principal giả**: không kiểm tra token revocation thật.
19. **Không phân biệt lệnh revoke success và hiệu lực revoke đã được xác minh**: nhiều provider/store có thể pending.
20. **Cho người bị khóa tự unlock bằng session cũ**: bypass assurance/recovery policy.

## 13. Checklist kết luận chẩn đoán

- [ ] Đã xác định nguồn Authentication của request sống sót: session, remember-me, JWT, opaque, refresh, IdP hay API key.
- [ ] Đã xác nhận logout handler/HTTP method/CSRF/filter chain thực sự chạy trên endpoint.
- [ ] Nếu yêu cầu global logout, đã tìm/xóa session ở shared repository với principal index đúng tenant.
- [ ] Mọi protected request critical kiểm tra account status/revocation version theo chính sách; không chỉ lúc login ban đầu.
- [ ] AS chặn refresh-token family cũ sau lock và chống refresh/revoke race.
- [ ] JWT offline có short TTL được phê duyệt hoặc denylist/security version enforcement trên **mọi** Resource Server.
- [ ] Opaque introspection phản ánh revoke và cache TTL phù hợp SLA.
- [ ] Remember-me, OAuth authorized clients và IdP SSO đã được xử lý theo phạm vi và khả năng provider.
- [ ] Outbox/retry/idempotency không xóa nhầm session mới được cấp hợp lệ sau recovery.
- [ ] Đã thử old credentials trên hai client/nhiều node và ghi revocation lag thực tế.
- [ ] Không log raw credential, không lộ account existence/reason nội bộ, vẫn giữ audit.
- [ ] Có runbook phục hồi và quy trình tranh chấp/false positives cho người dùng hợp lệ.

**Ghi nhớ:** một lệnh khóa account hay logout chỉ là **ý định thay đổi quyền truy cập**. Nó chỉ trở thành **thu hồi hiệu quả** khi **mọi đường xác thực còn sống** cùng kiểm tra trạng thái hoặc được xóa ở đúng nơi, và kiểm thử hậu xử lý chứng minh credential cũ không thể tiếp tục mở tài nguyên ngoài cửa sổ rủi ro được chấp nhận.

## 14. Tài liệu chính thức

- Spring Security 6.5 — Handling Logouts: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — `SecurityContextLogoutHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html
- Spring Session 3.5 — `FindByIndexNameSessionRepository`: https://docs.spring.io/spring-session/reference/3.5/api/java/org/springframework/session/FindByIndexNameSessionRepository.html
- Spring Session — Using SessionRepository and Principal Index: https://docs.spring.io/spring-session/reference/api.html
- Spring Security — JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security — Opaque Token Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- RFC 7009 — OAuth2 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009.html
- RFC 7662 — OAuth2 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662.html
- RFC 6750 — OAuth2 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
