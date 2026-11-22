# Thu hồi phiên, khóa, token và yếu tố sau thay đổi tài khoản

## 1. Mục tiêu của vòng đời tài khoản

Trong Spring Security, việc một người dùng thay mật khẩu, bị khóa, bị xóa vai trò hoặc thay thiết bị xác thực MFA không tự làm mọi bằng chứng xác thực đã phát hành trước đó mất hiệu lực. Một hệ thống có thể đồng thời tồn tại:

- HTTP session của nhiều trình duyệt và nhiều thiết bị.
- Remember-me cookie hoặc trusted-device token.
- OAuth2 refresh token và access token, có thể là JWT hoặc opaque.
- API key, personal access token, khóa của service account, certificate mTLS.
- TOTP seed, WebAuthn credential, recovery codes, pending challenges và bằng chứng step-up.
- Phiên đăng nhập tại Identity Provider và phiên cục bộ của các ứng dụng SSO.

**Vấn đề:** thay đổi trạng thái tài khoản ở cơ sở dữ liệu **không có nghĩa** mọi session, JWT, API key, remember-me token hay phiên SSO sẽ bị từ chối ngay. Mỗi loại credential có nơi lưu, thời hạn, nhà phát hành và ranh giới tin cậy khác nhau.

Ví dụ: tài khoản được disabled lúc 10:00, nhưng một access JWT đã cấp có `exp=10:30` vẫn có thể được API chấp nhận nếu resource server chỉ kiểm tra chữ ký và thời hạn. Đồng thời một HTTP session khác vẫn giữ `SecurityContext` với quyền cũ. Cần xác định rõ **đường thu hồi, thời điểm enforce và SLA truyền trạng thái**.

Mục tiêu bài học:

1. Phân loại sự kiện thay đổi tài khoản và phạm vi credential cần thu hồi.
2. Phân biệt thu hồi **credential gốc**, **session**, **token**, **MFA factor** và **authorization**.
3. Giải thích giới hạn của Spring Security session/logout, JWT offline validation và OAuth2 revocation.
4. Thiết kế đồng bộ nhiều instance, nhiều resource server, IdP/SSO và cache, không bỏ sót đường truy cập.
5. Đưa ra ví dụ Java 17 và các kiểm thử chứng minh hệ thống thực sự từ chối credential cũ.

## 2. Thu hồi cái gì, ở đâu và bằng cách nào?

| Đối tượng | Nguồn trạng thái | Cơ chế thu hồi |
|---|---|---|
| **Browser HTTP session** | Servlet container / Spring Session Redis, JDBC… | Xóa server-side session đúng ID; chặn cookie cũ; xử lý SecurityContext. |
| **Session principal/authorities** | `SecurityContextRepository` / session store | Invalidate session hoặc buộc cập nhật principal/quyền sau khi authzVersion đổi. |
| **Remember-me** | Persistent token DB hoặc cookie có chữ ký | Xóa persistent series/token, invalidate cookie; token stateless cần cơ chế riêng. |
| **Refresh token** | OAuth2 Authorization Server / grant store | Revoke token, grant/family; chặn refresh với account disabled. |
| **Access JWT** | Resource server thường tự xác minh offline | TTL ngắn hoặc online epoch/status, denylist `jti`, introspection/central gate. |
| **Opaque access token** | Authorization Server + introspection | Revoke tại AS, RS giảm/invalidates cache `active`. |
| **API key** | Credential store với `key_id` + verifier | Đánh dấu revoked/expired, kiểm tra owner/tenant active, invalidates cache. |
| **MFA authenticator** | Enrollment TOTP/WebAuthn/device store | Disable/remove đúng authenticator ID, xóa/reissue codes khi phù hợp. |
| **MFA proof/challenge** | Challenge/step-up store | Hủy challenge còn chờ, invalidate proof đã xác minh và elevated grant. |
| **IdP SSO session** | OpenID Provider/IdP | Logout tại IdP, federation logout; không đồng nhất với RP session. |
| **Local RP session** | Ứng dụng Spring Boot/SaaS | Xóa local session; hỗ trợ OIDC back-channel logout nếu tích hợp. |
| **Service secret/certificate** | Secret manager, KMS, PKI | Rotate/revoke key/cert hoặc cập nhật trust; tách khỏi logout người dùng. |

**Không có một nút “revokeAll” của framework tự giải quyết mọi mục trên.** Ứng dụng phải liên kết các thành phần bằng chính sách lifecycle và những enforcement point có khả năng từ chối quyền truy cập cũ.

## 3. Sự kiện khác nhau, phạm vi revoke khác nhau

| Sự kiện | Browser sessions | OAuth grants/tokens | API key | MFA enrollment / proofs |
|---|---|---|---|---|
| Logout thiết bị hiện tại | Hủy session hiện tại. | Revoke grant cùng client/device nếu policy. | Thường giữ key độc lập. | Hủy proof gắn session; giữ enrollment. |
| Logout all devices | Hủy mọi session của user. | Revoke grants/families, xử lý access tokens. | Theo policy và ownership của key. | Hủy proofs/trusted-device context. |
| Đổi mật khẩu tự nguyện | Thường revoke phiên khác; có thể tạo phiên mới sau re-auth. | Revoke refresh grants/epoch nếu yêu cầu. | Không tự xóa khóa integration độc lập. | Invalidate recent proof; giữ factor nếu an toàn. |
| Password reset vì nghi compromise | Hủy toàn bộ session. | Revoke refresh tokens, hạn access tokens cũ. | Đánh giá revoke mọi credential liên quan. | Hủy pending challenges/proofs, đánh giá enrollment. |
| Account disabled | Hủy mọi phiên, chặn login mới. | Không cấp refresh/access mới; RS từ chối token cũ theo SLA. | Vô hiệu hóa key theo owner/account status hoặc revoke. | Không chấp nhận factor/proof, hủy challenge. |
| Thay role/quyền | Tái đánh giá authorities. | Token cũ có thể chứa role stale; cần authzVersion/TTL. | Giảm scopes ngay ở enforcement. | Không nhất thiết xóa enrollment. |
| Thay/xóa MFA factor | Có thể buộc re-auth ở phiên rủi ro. | Revoke grants phụ thuộc assurance cũ. | Không mặc định ảnh hưởng M2M key. | Revoke factor, backup codes, challenges và proof tương ứng. |
| Security incident | Hủy toàn bộ phiên. | Revoke grants/families và chặn access tokens. | Rotate/revoke secrets/certs liên quan. | Disable compromised authenticators, re-enroll. |
| Đổi tên hiển thị | Thường giữ. | Thường giữ. | Giữ. | Giữ. |

Đây là **một bảng chính sách tham khảo**, không phải tiêu chuẩn bắt buộc. Điều cốt lõi là xác định rõ **sự kiện nào có ý nghĩa compromise, quyền nào phải mất, và những credential nào độc lập với mật khẩu cá nhân**.

Không tự xóa một service integration đang hoạt động khi người dùng chỉ đổi tên; ngược lại, không giữ API key có toàn quyền nếu owner đã bị vô hiệu hóa vì xâm nhập.

## 4. Kiến trúc nguồn sự thật và thu hồi

Một kiến trúc điển hình:

~~~text
[Admin / User / HRIS / Security operations]
                   |
                   v
           Account Lifecycle Service
             - validate actor/policy
             - update account state
             - bump security/authz epochs
             - persist outbox event
                   |
          +--------+----------+
          |                   |
          v                   v
   Access enforcement      Async revocation
    - account active?       - sessions
    - token epoch?          - remember-me
    - current roles?        - refresh grants
    - MFA status?           - API keys
          |                 - IdP/RP logout
          v                   |
     allow / deny         ACK / retry / audit
~~~

Có hai đường kiểm soát bổ trợ:

- **Đường quyết định đồng bộ:** tại mỗi request cần xét trạng thái account/epoch/permission đang có hiệu lực. Với API nhạy cảm, nếu không thể xác minh trạng thái phải fail closed theo policy.
- **Đường dọn dẹp bất đồng bộ:** xóa session, grants, MFA proof và revoke API key theo sự kiện đã commit, retry/reconciliation cho đến khi mọi thành phần xác nhận.

Nếu chỉ dựa vào event phát qua queue, có một khoảng trễ. Nếu chỉ dựa vào check online nhưng không dọn session/token, hệ thống vẫn giữ rác bảo mật và có thể tồn tại endpoint bỏ qua gate. Hai đường này nên bổ sung cho nhau.

### Version/epoch khác thời gian

Một `securityEpoch` tăng khi credential/assurance bị thay đổi. Một `authorizationVersion` tăng khi role/tenant/policy thay đổi. Các token và session có thể chứa version được phát hành. Resource server so sánh với version hiện tại để quyết định.

~~~text
token issued: user=usr-1042, securityEpoch=5, authzVersion=11
admin revokes admin role:
  account.authzVersion = 12
resource server:
  validate token signature, issuer, aud, exp
  fetch current account state
  reject token version 11 (or recompute permissions)
~~~

**Nếu API không kiểm tra version hiện tại, tăng version trong DB không làm JWT cũ vô hiệu.** Epoch là một cách biểu diễn policy, không phải phép màu mật mã.

## 5. HTTP session trong Spring Security và các giới hạn của logout

Spring Security Servlet lấy `Authentication` từ `SecurityContext`; context có thể được lưu vào HTTP session bởi `SecurityContextRepository` theo cấu hình. Khi user đăng nhập ở nhiều browser/thiết bị, có thể có nhiều session khác nhau.

### Logout một session

Spring Security `logout()` có thể invalidate current HTTP session, xóa SecurityContext và thực hiện logout handlers. Xóa cookie giúp browser không tiếp tục gửi session ID, nhưng **chỉ xóa cookie phía client không đủ** nếu attacker còn giữ một bản sao. Session ID đó phải bị từ chối **server-side**.

Mã:

~~~java
SecurityContextHolder.clearContext();
~~~

chỉ clear context của luồng request hiện tại, **không tự hủy toàn bộ session lưu trong Redis/JDBC hoặc session trên thiết bị khác**.

### Logout all sessions

Cần một cơ chế xác định **tất cả session của một user**, lý tưởng sử dụng **immutable internal user ID** làm principal index. Với Spring Session Redis/JDBC và `FindByIndexNameSessionRepository` có thể tìm session theo principal (khi index đã được cấu hình), rồi delete theo session ID.

~~~java
// Spring Session integration snippet, cần dependency/config cụ thể:
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

public class AllSessionsRevoker<S extends Session> {
    private final FindByIndexNameSessionRepository<S> repository;

    public AllSessionsRevoker(FindByIndexNameSessionRepository<S> repository) {
        this.repository = repository;
    }

    public void revokeAll(String stableUserId) {
        Map<String, S> sessions =
                repository.findByPrincipalName(stableUserId);
        for (String sessionId : sessions.keySet()) {
            repository.deleteById(sessionId);
        }
    }
}
~~~

Đây là code tích hợp: không chạy độc lập nếu thiếu Spring Session, repository/index. Cần kiểm chứng principal index chính xác, không dựa email có thể đổi; kiểm thử multi-instance/replica, TTL và request đang chạy.

### `SessionRegistry.expireNow()` không hủy ngay mọi session

Spring Security có `SessionRegistry` và `SessionInformation.expireNow()`. Thao tác này đánh dấu phiên expired; filter quản lý phiên (chẳng hạn `ConcurrentSessionFilter` khi được cấu hình) có thể phát hiện ở request tiếp theo. Nó **không tự hủy HttpSession ngay lập tức ở mọi node**, và không có nghĩa access JWT/refresh token đã bị revoke.

Tương tự, `maximumSessions(1)` chỉ là session concurrency control trong cấu hình phù hợp, không thay endpoint “đăng xuất mọi thiết bị”. Nếu cần chặn ngay request sắp tới, vẫn phải kiểm tra account status/security epoch theo SLA.

## 6. Remember-me và trusted-device state

Remember-me cho phép browser khôi phục một mức login sau khi session thông thường hết hạn. Nếu password reset chỉ xóa session mà **persistent remember-me token còn active**, attacker có thể tiếp tục đăng nhập lại.

- **Persistent-token remember-me:** hủy record token/series của user tại server; xóa cookie khi có cơ hội. Cookie bị copy vẫn bị chặn nếu record đã revoke.
- **Stateless remember-me:** thu hồi chọn lọc khó hơn; có thể cần auth epoch, khóa ký rotate với blast radius đã tính hoặc TTL ngắn. Không coi xóa cookie hiện tại là revoke toàn hệ thống.
- **Trusted-device:** cookie/device record thường hỗ trợ giảm MFA friction; nó **không** đồng nghĩa MFA proof đủ mới. Khi mất thiết bị hoặc reset MFA, xem xét invalidate trusted devices và các phiên dựa trên chúng.

Nếu user đổi password trong một session vừa được re-auth, ứng dụng có thể giữ session ấy sau regenerate ID và update security version; phải có policy rõ để không giữ credential cũ ngoài ý muốn.

## 7. OAuth2 refresh token, authorization grant và token family

Refresh token thường sống lâu hơn access token. Nếu bị lộ, người nắm giữ có thể xin access token mới cho đến khi bị revoke/hết hạn. Vì vậy account disable hoặc password reset thường cần **ngăn token refresh trước tiên**, song song xử lý access token hiện hữu.

Theo **RFC 7009**, OAuth2 authorization server có token revocation endpoint. Tác dụng đối với token liên quan/grant phụ thuộc chính sách của server; **một lệnh revoke một token không mặc nhiên tương đương revoke toàn bộ token của mọi client**.

Thông tin quản trị thường gồm:

~~~text
grantId, clientId, subjectId, tenantId
refreshTokenId / tokenFamilyId
issuedAt, expiresAt, revokedAt
rotationCounter, reuseDetectedAt
scopes, audiences, assuranceContext
~~~

### Rotation và reuse detection

~~~text
RT-1 (active)
  | successful refresh
  v
RT-1 (consumed)
RT-2 (active, same family)
  | attacker presents RT-1 again
  v
reuse detected -> revoke family / require re-auth
~~~

Cần quản lý atomic transition, concurrent refresh, grace policy phù hợp loại client và incident response. Không để hai request đồng thời tạo hai refresh token hợp lệ không được quản lý; nhưng cũng phải xét retry do lỗi mạng để tránh khóa nhầm người dùng vô tội.

**Sau account disable**, authorization server phải từ chối phát token mới **dù refresh token cũ còn record trong DB**. Lệnh cleanup token không thay kiểm tra account status lúc refresh.

Với JWT access token đã phát hành, revoke refresh chỉ ngăn **phát token mới**, không nhất thiết làm access token cũ mất hiệu lực.

## 8. Access token JWT tự chứa: có thể vẫn hợp lệ sau khi account bị khóa

Ví dụ:

~~~text
10:00:00  JWT issued, exp = 10:15:00
10:02:00  User disabled
10:05:00  Resource Server validates signature, aud, iss, exp
10:05:01  Nếu không kiểm tra current account state -> JWT vẫn có thể được nhận
~~~

JWT ký hợp lệ và chưa hết hạn không chứng minh user hiện đang active, role vẫn còn hoặc MFA enrollment chưa bị revoke. Những phương án chính:

| Phương án | Ưu điểm | Giới hạn |
|---|---|---|
| Access-token TTL ngắn | Giảm khoảng phơi lộ nếu không có online state. | Không revoke ngay, trễ tối đa đến deadline token. |
| Denylist `jti`/fingerprint | Vô hiệu một token cụ thể. | Cần store, TTL/cache và mỗi RS tra nó. |
| Account security epoch | Vô hiệu nhiều token của user qua một version. | RS phải đối chiếu online, chịu latency/cache failure. |
| Authz policy theo request | Hạn quyền stale, kiểm tra tenant/resource đúng hiện tại. | Phụ thuộc nguồn policy và availability. |
| Opaque token/introspection | AS có thể trả `active=false` sau revoke. | Kết quả cache có thể stale, tăng network dependency. |
| Gateway/central enforcement | Dễ tập trung kiểm tra. | Phải chặn đường bypass gateway. |

Không dùng ID Token OIDC như bearer access token của API. Token JWT phải được kiểm tra signature, issuer, audience cho API, thời hạn và loại token **trước** khi xem account epoch/roles.

**Đổi JWT signing key của cả hệ thống để revoke một người dùng là cách có blast radius lớn**, có thể ảnh hưởng mọi token và JWKS cache. Key rotation xử lý riêng khi signing key bị lộ hoặc theo lịch, không thay per-account revocation.

## 9. Opaque access token và thời gian cache introspection

Với opaque token, resource server có thể gọi OAuth2 introspection (RFC 7662) để nhận `active`, subject, client, scopes… từ Authorization Server đáng tin. Khi token revoked, introspection *mới* sẽ phản ánh inactive.

Nhưng nếu resource server cache `active=true` trong 2 phút, **hiệu lực revoke quan sát được có thể trễ đến 2 phút**. Phải đặt cache TTL/invalidation phù hợp security SLA.

Nếu AS/introspection service không sẵn sàng, cần chính sách fail closed cho endpoint nhạy cảm, không cho qua với một kết quả active cũ đã vượt thời gian cho phép. Không tin JSON `active=true` do client gửi.

Revocation ở AS và enforcement ở RS là hai điểm khác nhau: **SLA phải đo tại API thực sự phục vụ request**.

## 10. API key, personal access token và khóa dịch vụ

API key có thể gắn user, tenant, integration hoặc service account. Một key của chương trình đồng bộ đơn hàng có thể vẫn cần hoạt động khi nhân viên sở hữu tài khoản **đổi password tự nguyện**, nhưng sẽ không an toàn nếu owner bị disabled do compromise.

Một credential table (PostgreSQL minh họa):

~~~sql
CREATE TABLE api_credentials (
    key_id          VARCHAR(64) PRIMARY KEY,
    owner_id        VARCHAR(80) NOT NULL,
    tenant_id       VARCHAR(80) NOT NULL,
    verifier        BYTEA NOT NULL,
    status          VARCHAR(16) NOT NULL,
    issued_at       TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    security_epoch  BIGINT NOT NULL
);
~~~

Nếu server chỉ cần kiểm tra bearer API key, có thể lưu public `key_id` và hash/HMAC verifier của secret đủ ngẫu nhiên, thay vì plaintext. Tuy nhiên việc xác minh credential không đủ: **mỗi request** phải xét `ACTIVE`, expiry, owner/tenant status, permissions và policy epoch nếu cần.

Phân biệt:

- **Account lock:** trạng thái user/owner, không phải xóa mọi khóa vật lý.
- **API key revocation:** vô hiệu đúng key ID/credential.
- **Signing key rotation:** thay khóa ký JWT hoặc client assertion; cần cập nhật `kid`/JWKS/trust tương ứng.
- **mTLS certificate revocation:** xử lý PKI, CA/trust, OCSP/CRL hoặc short-lived certificates theo hạ tầng.
- **TOTP secret reset:** thay enrollment factor, không phải JWT signing key.

Không coi mỗi thao tác trên là “xóa session”.

## 11. MFA factor enrollment, challenges, proofs và recovery codes

**Authenticator đã đăng ký** (TOTP seed, WebAuthn public key, push device) khác với **challenge** đang chờ và **proof** rằng user vừa xác minh một yếu tố.

~~~text
Enrolled authenticator (TOTP / WebAuthn / device)
          |
          v
Challenge issued -> user presents response
          |
          v
Verifier validates and consumes challenge
          |
          v
Verified factor proof (verifiedAt, method, session, purpose)
          |
          v
Step-up authorization with separate freshness/invalidation
~~~

Khi password thay đổi, thường cần invalidate **step-up proofs** và xem xét các sessions liên quan; không mặc định xóa enrollment TOTP/WebAuthn nếu không có dấu hiệu nó bị xâm phạm.

Khi **mất điện thoại MFA** hoặc xóa authenticator:

1. Verify actor và recovery/step-up đủ mạnh; không chấp nhận một session cũ vô điều kiện.
2. Disable đúng authenticator ID, bảo đảm seed/credential không còn được chấp nhận.
3. Hủy pending challenges sử dụng authenticator đó; kiểm soát concurrency.
4. Invalidate verified-factor proofs/elevated grants đã phát từ authenticator.
5. Thu hồi hoặc phát lại recovery codes/trusted devices nếu policy quy định.
6. Audit và gửi thông báo bảo mật; xét session/token có assurance cũ, yêu cầu re-auth.

Không cập nhật `verifiedAt` chỉ vì refresh access token hoặc mở form. Một boolean `mfa=true` lưu trong JWT không tự thu hồi được nếu RS không có logic xét trạng thái/factor version.

## 12. OIDC SSO: phiên IdP và phiên ứng dụng không phải cùng một thứ

Khi đăng nhập qua OIDC, có **IdP/OpenID Provider session** và **local Relying Party (RP) session**. Kết thúc một phiên không có nghĩa phiên còn lại tự biến mất.

Các cơ chế OIDC thường dùng:

- **RP-Initiated Logout:** RP yêu cầu OP kết thúc phiên theo profile/endpoint hỗ trợ.
- **Front-Channel Logout:** thông báo qua browser, phụ thuộc hành vi user agent/cookie.
- **Back-Channel Logout:** OP gửi **Logout Token đã ký** đến endpoint RP, RP xác minh và hủy local sessions phù hợp.
- **Token revocation:** OAuth2 grants/refresh/access tokens là lớp khác.

OIDC Back-Channel Logout 1.0 dùng JWT Logout Token có `iss`, `aud`, `iat`, `events` và ít nhất `sub` hoặc `sid`. RP phải validate signature, issuer, audience, token purpose/event, thời gian, và xử lý replay theo policy trước khi hủy sessions.

~~~text
IdP -> signed Logout Token -> RP back-channel endpoint
                                  |
                           verify token trust
                                  |
                           find sessions by
                         (iss, sub) and/or (iss, sid)
                                  |
                            invalidate sessions
                                  |
                           audit without token
~~~

Không tin một request `POST /logout-all?user=admin` do client tùy ý gửi; không dùng `sub` đơn lẻ khi có nhiều issuer/tenant. Spring Security có các điểm tích hợp OIDC và Spring Session, nhưng phải kiểm tra phiên bản/configuration thực tế.

Một sự kiện deprovision từ HRIS/SCIM có thể cập nhật account state, **không phải tự thân là logout protocol**. Để đảm bảo offboarding, phải chặn account ở ứng dụng/RS và xử lý session/token còn tồn tại.

## 13. Password change và password reset: thứ tự công việc

Một luồng an toàn:

~~~text
User requests password change / recovery
      |
      v
Verify correct actor, recent assurance, password policy
      |
      v
Begin DB transaction
  - write new password hash (strong PasswordEncoder)
  - bump account securityEpoch / credentialVersion
  - record security event in transactional outbox
Commit
      |
      v
Enforcement gate rejects old epochs
      |
      +--> revoke sessions / remember-me
      +--> revoke refresh grants / token families
      +--> invalidate step-up proofs / recovery tokens
      +--> evaluate API keys and IdP SSO
      +--> notify account owner and audit
~~~

Đối với **password reset khẩn** nên revoke all sessions theo policy. Với **self-service password change sau MFA**, có thể giữ current session sau khi regenerate session ID và nâng epoch; phải bảo đảm phiên cũ ở thiết bị khác bị vô hiệu và app không vô tình cấp quyền từ security context cũ.

Các side effects không cùng DB transaction nên dùng durable outbox + retry/reconciliation. Không báo “đã logout tất cả thiết bị” chỉ vì event mới enqueue nếu chính sách yêu cầu sự bảo đảm mạnh hơn.

### Request đang chạy và TOCTOU

Một request approve có thể được authorized lúc 10:01, account bị disabled 10:02, sau đó request commit 10:03. Với thao tác nhạy cảm, cần **recheck account status/epoch và policy ngay trước commit**, có locking/transaction phù hợp. Kiểm tra ở filter đầu request chưa đủ để bảo vệ mọi thao tác dài.

## 14. Disable, lock, suspend và delete khác nhau

| Trạng thái | Ý nghĩa nghiệp vụ thường gặp | Tác động gợi ý |
|---|---|---|
| `ACTIVE` | Account có thể authentication nếu đạt policy. | Xác thực + phân quyền bình thường. |
| `LOCKED` | Có thể do login failures hoặc rủi ro. | Từ chối login; xử lý phiên đang có theo chính sách. |
| `SUSPENDED` | Tạm dừng quyền truy cập. | Chặn login, refresh, API keys và sessions theo scope định nghĩa. |
| `DISABLED` | Không còn được phép sử dụng hệ thống. | Fail closed trên mọi đường truy cập liên quan. |
| `DELETED/DEPROVISIONED` | Chấm dứt account. | Revoke credentials, giữ audit/tombstone theo retention. |

Các flag `UserDetails.isEnabled()` và `isAccountNonLocked()` thường được xét **khi authentication provider chạy**. Không có nghĩa mỗi HTTP request đã có session/JWT sẽ gọi lại user details hoặc kiểm tra cờ này. Cần một **authorization/account-status gate** nếu muốn chặn hiệu lực ngay.

### Offboarding minh họa

1. HR/IdP xác nhận user ID/tenant bằng nguồn đáng tin.
2. Account service commit `DISABLED` và tăng `securityEpoch`.
3. Auth server ngừng phát hành token mới.
4. Hủy sessions, remember-me, refresh families, MFA challenges/proofs.
5. Revoke API keys thuộc owner theo chính sách; chuyển ownership các integration riêng nếu được duyệt.
6. Resource servers từ chối JWT cũ qua online state/version hoặc cơ chế tương đương.
7. IdP/SCIM/federated logout thực thi theo hợp đồng.
8. Audit và reconcile để tìm credential/phiên bỏ sót.

Không dùng email làm khóa liên kết account khi có nhiều IdP hoặc sau khi người dùng đổi email. Dùng immutable internal user ID và external identity keys có namespace thích hợp.

## 15. Thay role/tenant: thu hồi authorization dù authentication còn hợp lệ

User có thể vẫn đăng nhập đúng người nhưng không còn quyền `PAYMENT_APPROVE` sau khi đổi team. Nếu JWT hoặc session chỉ lưu authorities snapshot tại thời điểm login, quyền cũ có thể tồn tại quá lâu.

Giải pháp:

- **Nạp policy hiện tại** tại endpoint/hành động quan trọng.
- Dùng `authzVersion` hoặc permissions epoch, so sánh online với account state.
- Hủy hoặc refresh sessions khi quyền thay đổi lớn.
- JWT TTL ngắn nếu policy chấp nhận độ trễ; với high-risk cần online enforcement.
- Đối chiếu tenant trong credential và resource, không lấy tenant từ header do client tự cung cấp.

Ví dụ:

~~~text
Access token: user=usr-1042, tenant=A, authzVersion=17
Admin removes role PAYMENT_APPROVE:
  account.authzVersion = 18
API request with v17:
  validate JWT and compare current version
  DENY or require refresh with v18 policy
~~~

**Không giải quyết stale role bằng JWT signature key rotation toàn bộ hệ thống** trừ khi signing key thực sự có vấn đề.

## 16. Event-driven revocation: idempotency, ordering và outbox

Một sự kiện nên có:

~~~json
{
  "eventId": "evt-8d12",
  "type": "ACCOUNT_DISABLED",
  "subjectId": "usr-1042",
  "tenantId": "tenant-a",
  "accountVersion": 42,
  "effectiveAt": "2026-11-06T10:00:00Z",
  "reasonCategory": "SECURITY_INCIDENT"
}
~~~

Các consumer xử lý:

- Idempotent: event v42 đến hai lần không tạo token mới, không lỗi nguy hiểm.
- Monotonic: event v41 đến sau v42 không làm trạng thái quay lùi.
- Re-enable v43 không tự hồi sinh credential v42 đã revoke.
- Durable retry với backoff; dead letter được giám sát.
- Reconciliation định kỳ giữa account state và active session/grant/key indexes.

Dùng **transactional outbox** để đảm bảo account state và ý định revoke được commit cùng nhau, rồi worker gửi event. Nếu queue lỗi đúng thời điểm disable mà event chỉ được phát sau commit từ memory, có thể mất lệnh. Outbox giảm rủi ro đó.

Tách **command** ("hãy thu hồi session") khỏi **event** ("account đã disabled tại version 42") và **audit** (ai đã yêu cầu, vì sao, hệ thống nào đã xác nhận). Audit không được chứa bearer tokens/secret.

## 17. Spring Security: enforce account state tại method boundary

Trong Spring Boot 3.x/Spring Security 6.x, `Authentication.isAuthenticated()` không đủ để chặn account disabled hoặc permission vừa bị thu hồi. Có thể xây một policy bean dùng **internal user ID đáng tin**, không lấy user ID từ request parameter.

Ví dụ sau là **mã tích hợp**, cần service/identity mapping do ứng dụng triển khai, không phải chương trình `javac` độc lập:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("accountAccessPolicy")
public class AccountAccessPolicy {
    private final AccountStateService states;

    public AccountAccessPolicy(AccountStateService states) {
        this.states = states;
    }

    public boolean active(Authentication auth) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }
        String userId = resolveTrustedInternalUserId(auth);
        return userId != null && states.isActive(userId);
    }

    private String resolveTrustedInternalUserId(Authentication auth) {
        // Tùy loại internal principal/Jwt đã được verify.
        // Không lấy ID từ header/JSON do client tự khai.
        throw new UnsupportedOperationException("integration required");
    }
}
~~~

Đây chỉ là điểm nối minh họa; production phải thay method `resolveTrustedInternalUserId` bằng code thực và nguồn state đáng tin.

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    @PreAuthorize(
        "hasAuthority('PAYMENT_APPROVE') and " +
        "@accountAccessPolicy.active(authentication) and " +
        "@factorPolicy.recentForPayment(authentication)")
    public void approve(String paymentId) {
        // Kiểm tra resource/tenant, securityEpoch, factor proof
        // và business invariants tại điểm commit.
    }
}
~~~

Cần `@EnableMethodSecurity` và kiểm thử Spring proxy interception; **self-invocation** trong cùng bean có thể bỏ qua method-security proxy. `hasAuthority` chỉ kiểm tra authority trên authentication hiện tại, còn policy bean/transaction service mới áp cập nhật lifecycle.

### Resource server JWT

Nếu token chứa `securityEpoch`, một `JwtAuthenticationConverter` hoặc authorization service có thể xác định current user/epoch **sau khi JwtDecoder đã verify token**. Không tin claim email tùy ý làm khóa user; ràng buộc issuer, subject, tenant và internal link. Với endpoint nhạy cảm có thể dùng dynamic AuthorizationManager hoặc method policy để tránh stale permissions.

### Session store

Nếu ứng dụng dùng Spring Session Redis/JDBC, shared repository/index có thể hỗ trợ revoke all sessions. Nếu chỉ dùng SessionRegistry local một node, phải bảo đảm các node khác được cập nhật; nếu không, logout all không có tính cross-node.

## 18. Java 17 độc lập: security epoch và hiệu lực của credential

Ví dụ Java 17 sau chỉ minh họa **đánh giá trạng thái**. Nó không xác minh chữ ký JWT, mật khẩu, HMAC API key, session cookie hoặc MFA thật. Điểm quan trọng là credential phát hành trước thời điểm account security epoch tăng sẽ bị từ chối **nếu verifier kiểm tra epoch**.

~~~java
import java.time.Instant;

public class AccountRevocationDemo {
    record BrowserSession(long issuedEpoch) {}
    record AccessToken(long issuedEpoch, Instant expiresAt) {}
    record FactorProof(long issuedEpoch, String method) {}
    record ApiKey(boolean revoked) {}

    static final class Account {
        private long epoch = 1;
        private boolean enabled = true;

        synchronized long currentEpoch() {
            return epoch;
        }

        synchronized boolean active() {
            return enabled;
        }

        synchronized void passwordChanged() {
            epoch++;
        }

        synchronized void disabled() {
            enabled = false;
            epoch++;
        }
    }

    static boolean browserValid(Account a, BrowserSession s) {
        return a.active() && s.issuedEpoch() == a.currentEpoch();
    }

    static boolean jwtValid(Account a, AccessToken t, Instant now) {
        return a.active() && t.issuedEpoch() == a.currentEpoch()
                && now.isBefore(t.expiresAt());
    }

    static boolean mfaProofValid(Account a, FactorProof p) {
        return a.active() && p.issuedEpoch() == a.currentEpoch()
                && p.method().equals("TOTP");
    }

    static boolean apiKeyValid(Account a, ApiKey k) {
        return a.active() && !k.revoked();
    }

    public static void main(String[] args) {
        Account account = new Account();
        Instant now = Instant.parse("2026-11-06T10:00:00Z");
        long v = account.currentEpoch();

        BrowserSession session = new BrowserSession(v);
        AccessToken jwt = new AccessToken(v, now.plusSeconds(900));
        FactorProof proof = new FactorProof(v, "TOTP");
        ApiKey integration = new ApiKey(false);

        System.out.println("initial browser: "
                + browserValid(account, session));
        System.out.println("initial jwt: "
                + jwtValid(account, jwt, now));
        System.out.println("initial factor: "
                + mfaProofValid(account, proof));

        account.passwordChanged();
        System.out.println("after password browser: "
                + browserValid(account, session));
        System.out.println("after password jwt: "
                + jwtValid(account, jwt, now.plusSeconds(1)));
        System.out.println("after password factor: "
                + mfaProofValid(account, proof));
        System.out.println("after password api key: "
                + apiKeyValid(account, integration));

        account.disabled();
        System.out.println("after disable api key: "
                + apiKeyValid(account, integration));
    }
}
~~~

Lưu đúng tên `AccountRevocationDemo.java` rồi chạy:

~~~bash
javac AccountRevocationDemo.java
java AccountRevocationDemo
~~~

**Stdout chính xác:**

~~~text
initial browser: true
initial jwt: true
initial factor: true
after password browser: false
after password jwt: false
after password factor: false
after password api key: true
after disable api key: false
~~~

Ý nghĩa: sau password change, phiên, JWT và MFA proof gắn epoch cũ bị từ chối. Theo policy minh họa, API key của integration độc lập không tự bị revoke chỉ do password change; khi account disabled thì API key cũng bị chặn bằng owner status.

**Lưu ý production:** trạng thái demo nằm trong một JVM, chưa giải quyết concurrency/distributed cache hay cấp phát token thật. Nếu resource server JWT chỉ validate signature/`exp` **mà không đối chiếu epoch**, câu lệnh `passwordChanged()` không làm JWT cũ mất hiệu lực. Security epoch phải được persist transactionally và enforcement/cache invalidation phải đáp ứng SLA.

## 19. SLA, giám sát và hậu kiểm thu hồi

Đừng đồng nhất “đã ghi revoke event” với “mọi request cũ đã bị chặn”. Nên đo:

1. `t0`: account update/securityEpoch được commit.
2. `t1`: request mới ở API/AS bắt đầu bị từ chối.
3. `t2`: các session, grants, keys, MFA proofs và RP sessions liên quan đã được cleanup hoặc đã có gate chặn.
4. `t3`: reconciliation xác nhận không còn credential trái chính sách.

Chỉ khi hệ thống thực sự đạt các mốc mới nên mô tả user-facing outcome là “đã đăng xuất tất cả thiết bị” theo nghĩa bảo mật. Nếu một JWT offline sống 15 phút và không kiểm tra state online, không thể đảm bảo thu hồi trong 30 giây chỉ bằng thay cột `enabled`.

Metrics gợi ý:

~~~text
account_security_change_total
revocation_event_lag_seconds
session_revocation_success_total
refresh_grant_revocation_failure_total
stale_access_token_rejected_total
disabled_account_access_attempt_total
mfa_proof_revocation_lag_seconds
revocation_reconciliation_discrepancy_total
~~~

Audit chứa actor, subjectId/tenant, reason category, eventId/version, outcome, timestamp, correlation ID nhưng **không ghi raw access/refresh token, session cookie, API key secret hoặc MFA recovery codes**.

## 20. Kiểm thử và những lỗi thường gặp

| Tình huống | Kỳ vọng |
|---|---|
| User logout browser A, browser B còn đăng nhập. | Logout một thiết bị chỉ ảnh hưởng A nếu policy. |
| User chọn logout all. | Cả A và B bị chặn; cookie cũ không khôi phục phiên. |
| Chỉ gọi `SecurityContextHolder.clearContext()`. | Test cho thấy chưa tự xóa sessions khác. |
| Gọi `SessionRegistry.expireNow()`. | Kiểm chứng filter/session infrastructure xử lý trên request tiếp theo. |
| Password reset thành công. | Các session, refresh grants, MFA proofs bị revoke theo policy. |
| Refresh token bị revoke, access JWT còn hạn. | API vẫn phải áp strategy cho JWT cũ, không suy từ refresh revoke. |
| JWT có epoch cũ sau password change. | RS check current epoch và từ chối. |
| JWT có role ADMIN cũ sau đổi quyền. | Không giữ quyền admin ngoài thời hạn policy. |
| Opaque introspection result đã cache. | Không vượt SLA thu hồi; cần invalidation/TTL. |
| Remember-me cookie từ thiết bị cũ. | Không đăng nhập lại sau incident/reset nếu policy revoke. |
| Account disabled nhưng API key row còn active. | API owner-status check vẫn từ chối, hoặc key bị revoke. |
| Xóa TOTP authenticator. | Challenges/proofs liên quan mất hiệu lực, seed không còn được tin. |
| Logout token OIDC giả mạo. | RP từ chối, không DoS user. |
| Back-channel logout hợp lệ với `iss/sub/sid`. | RP xóa đúng sessions, không nhầm issuer khác. |
| Event revoke được gửi hai lần. | Idempotent, không tạo credential mới hoặc lỗi nguy hiểm. |
| Event disable v42 đến sau enable v43. | Không áp stale event để vô hiệu phiên mới. |
| Queue outage sau account disable. | Outbox/retry xử lý, enforcement vẫn chặn theo version/state. |
| Request đã kiểm tra quyền trước disable nhưng commit sau. | TOCTOU guard ở business commit chặn theo policy. |
| User bị xóa rồi email được tái sử dụng. | Không gán credential cũ sang user mới cùng email. |
| Resource server không thể tra trạng thái. | Fail closed ở API nhạy cảm theo policy. |
| Re-enable account. | Không tự hồi sinh key/token/factor đã revoke trước đó. |

Các lỗi triển khai hay gặp: chỉ đổi password hash; chỉ xóa cookie hiện tại; tưởng logout ở IdP tự logout mọi RP; dùng JWT signing-key rotation để revoke một user; tăng auth version mà không có consumer kiểm tra; lưu stale account-active trong cache vô thời hạn; gom API key của service vào username/email; và thiếu audit/reconciliation.

## 21. Checklist vận hành

- [ ] Có ma trận sự kiện → session/remember-me/refresh/access/API-key/MFA/SSO phải revoke.
- [ ] Account status và security/authz epochs là trạng thái authoritative, được commit trước khi báo thành công.
- [ ] Tất cả login/token-refresh paths từ chối disabled account.
- [ ] Session store cross-node có principal index đáng tin để revoke all.
- [ ] Remember-me và trusted device được xử lý riêng khi reset/compromise.
- [ ] Refresh grants/families bị revoke và có reuse detection nếu hỗ trợ rotation.
- [ ] JWT/opaque tokens được xử lý theo SLA chấp nhận, không dựa duy nhất vào `exp` khi cần immediate deny.
- [ ] Resource servers vẫn kiểm tra signature, issuer, audience, expiry, token purpose và quyền tài nguyên.
- [ ] API keys kiểm tra owner/tenant/status hiện tại; service credential scope được định nghĩa.
- [ ] MFA authenticator khác với challenge/proof, có thể invalidate đúng loại.
- [ ] OIDC local session vs IdP session vs OAuth grants đã phân định rõ.
- [ ] Role/tenant change ảnh hưởng live authorization, không giữ snapshot quá hạn.
- [ ] Outbox, idempotency, version ordering, DLQ/retry và reconciliation được kiểm thử.
- [ ] Cache invalidation và network failure modes đáp ứng security SLA.
- [ ] High-risk business actions recheck quyền gần commit để tránh TOCTOU.
- [ ] Logs không có token, cookie, OTP, TOTP seed hay API key secret.
- [ ] Có quy trình emergency disable, rotate keys, re-enroll MFA và re-enable an toàn.
- [ ] Có multi-instance integration tests, event-race tests và monitoring hiệu quả thu hồi.

## 22. Kết luận

**Thay đổi tài khoản không tự thu hồi bằng chứng xác thực đã phát hành.** Cần kết nối account lifecycle với từng loại state: HTTP session, remember-me, refresh grant, access token, API key, MFA enrollment/proof và phiên SSO. Mỗi loại có nơi lưu và cách revoke riêng.

Công thức vận hành đáng tin cậy là **commit trạng thái account/epoch → enforce trạng thái mới ở request path → phát event revoke idempotent → cleanup các credential/phiên liên quan → audit/reconcile và kiểm thử SLA**. Đặc biệt với JWT tự chứa, chỉ đổi password hoặc revoke refresh token **không bảo đảm** JWT đang có mất hiệu lực nếu resource server không dùng thêm online status/epoch/denylist hoặc giới hạn TTL đã được chấp nhận.

Trong Spring Security, logout, `SecurityContext`, `SessionRegistry`, Spring Session, Resource Server, OAuth2 grants và MFA proof đều là các ranh giới riêng. Sự an toàn đến từ việc phối hợp chúng bằng chính sách rõ ràng, không từ một lệnh revoke giả định có thể thay thế tất cả.

## Tài liệu tham khảo

- [Spring Security – Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext, session concurrency và SessionRegistry.
- [Spring Security – Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): logout handlers, clearing contexts và session invalidation.
- [Spring Session – API](https://docs.spring.io/spring-session/reference/api.html): shared session stores và principal indexing.
- [Spring Security – Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation và policy extension.
- [RFC 7009 – OAuth2 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): revocation tại AS và tác động lên authorization grant.
- [RFC 7662 – OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): opaque token active state và caching.
- [RFC 9700 – OAuth2 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html): bearer/refresh-token risks và rotation.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html): Logout Token và RP sessions.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html): OP logout theo yêu cầu RP.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifecycle/revocation.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): account recovery, session và credential change.
- [OWASP – Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): MFA device removal, recovery, invalidation.
