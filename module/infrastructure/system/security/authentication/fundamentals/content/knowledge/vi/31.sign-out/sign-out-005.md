# Hủy phiên khi logout

> **Chương:** Đăng xuất  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích cách kết thúc phiên đúng cách khi người dùng đăng xuất: thu hồi trạng thái phía server, xóa cookie ở browser, xử lý token và phiên phân tán, đồng bộ logout giữa các ứng dụng, và kiểm tra rằng credential cũ không còn được chấp nhận.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt xóa cookie ở browser với hủy session phía server.
2. Mô tả vòng đời logout cho server-side session, access token, refresh token và phiên SSO.
3. Thiết kế logout an toàn, có CSRF protection, idempotent và có audit.
4. Hủy session trong hệ thống nhiều instance hoặc dùng distributed session store.
5. Hiểu giới hạn của việc thu hồi JWT self-contained và lựa chọn cơ chế phù hợp.
6. Xử lý logout một ứng dụng, logout khỏi IdP và logout toàn bộ thiết bị/phiên.
7. Xử lý request đang chạy, race condition, cache và browser back-forward cache sau logout.
8. Triển khai logout bằng Java/Spring Security và xây dựng ma trận kiểm thử.

## 2. Logout thực sự có nghĩa gì?

Khi người dùng đăng nhập, hệ thống tạo một hoặc nhiều credential duy trì quyền truy cập:

- Session ID trong cookie trỏ tới trạng thái phiên phía server.
- Access token cho phép gọi resource API.
- Refresh token có thể cấp access token mới.
- Cookie phiên tại Identity Provider (IdP).
- Local session riêng ở từng ứng dụng đã tham gia SSO.

**Logout an toàn là làm cho credential hoặc trạng thái phiên liên quan không còn được chấp nhận theo phạm vi logout đã chọn.** Browser không gửi cookie ở request sau chỉ là một phần của quá trình.

Ví dụ, An đăng nhập vào ứng dụng. Server tạo session S-123 và browser nhận cookie chứa session ID. An bấm Logout. Nếu ứng dụng chỉ xóa cookie trong browser nhưng session S-123 vẫn active ở server, attacker đã sao chép cookie trước đó vẫn có thể gửi nó và tiếp tục sử dụng phiên.

Vì vậy cần phân biệt:

| Hoạt động | Nơi thay đổi | Kết quả |
|---|---|---|
| Clear cookie | Browser | Browser hiện tại ngừng tự gửi cookie đó |
| Invalidate session | Session store/server | Session ID cũ không còn ánh xạ tới phiên hợp lệ |
| Revoke refresh token | Authorization server/token store | Không thể dùng refresh token đó để xin token mới |
| Revoke access token | Authorization/resource server theo cơ chế hỗ trợ | Token bị từ chối theo thời gian và phạm vi hệ thống |
| Clear client state | SPA/browser memory/cache | UI không tiếp tục hiển thị trạng thái user đã đăng nhập |
| IdP logout | Identity Provider | Kết thúc phiên đăng nhập tại IdP theo giao thức |
| Global logout | Nhiều RP/device/session | Thu hồi các phiên được bao phủ bởi yêu cầu |

Logout phải xác định rõ phạm vi: chỉ phiên hiện tại, mọi phiên của một ứng dụng, phiên IdP hay toàn bộ phiên và refresh token của tài khoản.

## 3. Mô hình logout với server-side session

Trong mô hình session truyền thống, browser giữ session ID; server giữ trạng thái xác thực, principal và metadata của session.

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant App as Application
    participant Store as Session store

    User->>Browser: Click Logout
    Browser->>App: POST /logout + session cookie + CSRF token
    App->>App: Validate request and identify current session
    App->>Store: Invalidate session ID
    Store-->>App: Session invalidated
    App-->>Browser: Clear session cookie + no-store response
    Browser->>Browser: Clear local authenticated state
    Browser-->>User: Redirect to public page
~~~

Thứ tự quan trọng:

1. Server xác minh request logout và xác định đúng session.
2. Server invalidate session ở nơi lưu trạng thái có thẩm quyền.
3. Server xóa hoặc thay cookie bằng Set-Cookie có cùng phạm vi cookie.
4. Browser xóa UI state và điều hướng tới trang công khai.
5. Hệ thống ghi audit event mà không lưu cookie/session secret.

Nếu session store không truy cập được, ứng dụng cần xử lý theo policy đã định nghĩa. Không được báo logout toàn hệ thống thành công nếu chỉ xóa cookie ở browser mà session server vẫn active.

## 4. Vì sao xóa cookie chưa đủ?

Cookie là bản sao credential ở browser. Việc xóa cookie chỉ tác động tới bản sao của browser hiện tại. Nó không xóa:

- Cookie đã bị attacker sao chép.
- Cookie trong browser profile hoặc thiết bị khác.
- Session record trong Redis/database/session cluster.
- Refresh token hoặc access token đã phát hành.
- Local session tại ứng dụng khác.
- Phiên đăng nhập tại IdP.

Ví dụ:

~~~text
Trước logout:
  Browser A -> Cookie SESSION=S-123
  Attacker  -> Copied cookie SESSION=S-123
  Server    -> Session S-123 = ACTIVE

Sau khi chỉ clear cookie ở Browser A:
  Browser A -> Cookie removed
  Attacker  -> Still has SESSION=S-123
  Server    -> Session S-123 = ACTIVE

Sau khi server invalidates session:
  Browser A -> Cookie removed
  Attacker  -> Still has old SESSION=S-123
  Server    -> Session S-123 = INVALID
~~~

Session ID cũ phải bị từ chối dù request đến từ browser nào hoặc IP nào. Không dựa vào việc người dùng đã đóng tab, đóng browser hay xóa lịch sử.

## 5. Xóa cookie đúng phạm vi

Browser xác định cookie theo các thuộc tính như name, domain/host-only, path và các chính sách liên quan. Khi xóa cookie, response phải đặt cookie cùng tên và phạm vi tương ứng với thời điểm cookie được tạo, rồi đặt Max-Age=0 hoặc Expires trong quá khứ.

Ví dụ:

~~~http
HTTP/1.1 302 Found
Set-Cookie: __Host-session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
Cache-Control: no-store
Location: /signed-out
~~~

Nếu cookie cũ được tạo với Path khác hoặc Domain attribute, chỉ gửi cookie rỗng với phạm vi không khớp có thể không xóa được bản cũ. Với prefix __Host-, cookie cần Secure, Path=/ và không có Domain.

Lưu ý:

- Không đưa session ID vào URL để hỗ trợ logout.
- Không dùng GET để thực hiện logout có thay đổi trạng thái; dùng POST hoặc cơ chế an toàn tương đương.
- Xóa đúng cookie session của ứng dụng; không xóa cookie không thuộc quyền quản lý của ứng dụng.
- Không coi Max-Age=0 là thu hồi session phía server.
- Cookie deletion phải hoạt động cả khi request đến qua reverse proxy/HTTPS termination.

## 6. CSRF protection cho logout

Logout cũng là thao tác thay đổi trạng thái. Nếu cookie được browser tự động gửi, một trang độc hại có thể cố gửi request logout thay user, gây forced logout hoặc phá gián đoạn thao tác.

Forced logout thường ít nghiêm trọng hơn chuyển tiền trái phép, nhưng có thể được dùng để gây denial of service, làm gián đoạn workflow hoặc kết hợp với login CSRF/session confusion.

Biện pháp:

- Dùng POST cho logout.
- Bật CSRF protection của framework cho cookie-based session.
- Dùng CSRF token hoặc cơ chế chống CSRF phù hợp.
- Cấu hình SameSite phù hợp nhưng không coi nó là lớp bảo vệ duy nhất.
- Kiểm tra Origin/Referer khi phù hợp với kiến trúc.
- Không để endpoint GET hoặc image/link đơn giản thực hiện logout.

Với API bearer-token không dùng cookie tự động gửi, threat model khác; vẫn cần authorization và bảo vệ token, nhưng CSRF cookie truyền thống có thể không áp dụng theo cùng cách.

## 7. Logout trong ứng dụng nhiều instance

Nếu ứng dụng chạy trên nhiều node, invalidate session chỉ trong bộ nhớ của một instance là chưa đủ. Request tiếp theo có thể được load balancer chuyển tới node khác vẫn giữ session cũ.

Các mô hình:

| Mô hình | Hành vi | Yêu cầu |
|---|---|---|
| In-memory session mỗi node | Session chỉ tồn tại ở một process | Sticky session không giải quyết thu hồi toàn cụm; cần đồng bộ hoặc session store chung |
| Shared Redis/session store | Các node đọc cùng trạng thái session | Invalidate tại store chung và xử lý cache |
| Database-backed session | Session được lưu trong DB | Transaction/conditional update và index phù hợp |
| Stateless JWT | Không có session record trung tâm mặc định | Cần chiến lược revoke/denylist/introspection hoặc lifetime ngắn |
| Hybrid | Cookie session và token downstream | Logout phải xử lý từng loại credential |

~~~mermaid
flowchart LR
    B["Browser"] --> LB["Load balancer"]
    LB --> N1["App node 1"]
    LB --> N2["App node 2"]
    LB --> N3["App node 3"]
    N1 --> S[("Shared session store")]
    N2 --> S
    N3 --> S
    N2 -->|"Invalidate session key"| S
    S -->|"Invalid state visible to all nodes"| N1
    S -->|"Invalid state visible to all nodes"| N3
~~~

Với shared store, mọi node phải quan sát trạng thái invalidated trong giới hạn consistency/SLA đã đặt ra. Nếu ứng dụng cache session cục bộ, cần xóa hoặc hết hạn cache đó khi session bị thu hồi.

## 8. Logout và JWT access token

JWT access token thường là self-contained: resource server xác minh chữ ký, issuer, audience và thời hạn mà không cần hỏi authorization server ở mỗi request.

Điều này giúp giảm phụ thuộc runtime, nhưng tạo giới hạn cho logout:

- Xóa cookie browser không làm JWT đã sao chép mất hiệu lực.
- Revoke refresh token ngăn cấp token mới, nhưng access token cũ có thể còn dùng được tới exp.
- Xoay signing key không phải cách thu hồi từng token thông thường và có thể ảnh hưởng diện rộng.
- Resource server có thể tiếp tục chấp nhận token nếu không có cơ chế kiểm tra trạng thái bổ sung.

Các chiến lược:

1. **Short-lived access token:** giảm cửa sổ token cũ còn hiệu lực.
2. **Opaque token + introspection:** resource server hỏi authorization server trạng thái token, có thể cache trong thời hạn giới hạn.
3. **Denylist/revocation store:** resource server kiểm tra token ID hoặc jti bị thu hồi; cần bảo vệ store và đồng bộ.
4. **Session/version claim:** token chứa session/account version và API so với trạng thái server-side khi cần.
5. **Event-driven revocation:** phát sự kiện tới API/gateway để cập nhật trạng thái; phải xử lý mất event và replay.
6. **Sender-constrained token:** DPoP hoặc mTLS giảm khả năng token bị sao chép dùng từ sender khác, nhưng không thay revoke.

Chọn chiến lược theo rủi ro, độ trễ revoke chấp nhận được, quy mô hệ thống và chi phí vận hành.

## 9. Refresh token revocation và token family

Refresh token thường sống lâu hơn access token và có khả năng cấp token mới. Logout cần revoke refresh token hoặc token family liên quan nếu ứng dụng có lưu.

Với refresh token rotation:

- Mỗi lần refresh thành công, token cũ bị vô hiệu và token mới được cấp.
- Nếu token cũ bị sử dụng lại, authorization server có thể phát hiện reuse và revoke token family theo policy.
- Logout nên revoke refresh token hiện tại hoặc family tương ứng, không chỉ xóa bản sao phía browser.
- Nếu refresh token được lưu server-side trong BFF, BFF cần xóa/revoke record và credential tại authorization server theo khả năng hỗ trợ.

Không log refresh token hoặc đưa token vào query string. Khi logout thất bại một phần, cần ghi nhận credential nào đã được revoke và credential nào còn có thể hoạt động.

## 10. OAuth token revocation endpoint

OAuth Token Revocation (RFC 7009) định nghĩa endpoint để client yêu cầu authorization server thu hồi token. Client gửi token và thông tin cần thiết theo cấu hình/provider.

Ví dụ minh họa:

~~~http
POST /oauth/revoke HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

token=<url-encoded-refresh-token>&token_type_hint=refresh_token
~~~

Không dùng URL thật hoặc token thật trong ví dụ. Endpoint và cách client authentication phụ thuộc authorization server.

Lưu ý:

- Client phải xác thực theo phương thức được đăng ký.
- Authorization server phải xử lý token thuộc client/issuer theo policy.
- Response thành công không tự bảo đảm mọi resource server đã ngừng chấp nhận JWT self-contained.
- Với opaque token/introspection, trạng thái inactive có thể được quan sát theo thời gian/cache.
- Client cần xử lý network failure và không báo đã revoke toàn hệ thống nếu chưa có xác nhận phù hợp.

## 11. Logout trong OpenID Connect SSO

OIDC có thể có nhiều phiên:

1. Phiên local tại RP (ứng dụng).
2. Phiên đăng nhập tại OpenID Provider (OP/IdP).
3. Access/refresh token đã cấp cho client.
4. Phiên local ở các RP khác.

Logout khỏi một RP không mặc định kết thúc các phiên còn lại.

### RP-initiated logout

OIDC RP-Initiated Logout cho phép RP điều hướng browser tới end-session endpoint của OP theo discovery/configuration. RP có thể gửi id_token_hint và post_logout_redirect_uri đã đăng ký; một số triển khai hỗ trợ state.

Trình tự khái quát:

1. RP invalidate local session.
2. RP xóa cookie local.
3. RP điều hướng browser tới OP end-session endpoint theo cấu hình.
4. OP xử lý phiên IdP và có thể yêu cầu tương tác/consent tùy policy.
5. OP chuyển về post-logout redirect URI đã đăng ký nếu được phép.

Local session cần được invalidate ngay cả khi OP logout endpoint lỗi hoặc browser không hoàn tất redirect. Không phụ thuộc hoàn toàn vào redirect tới IdP để bảo vệ ứng dụng hiện tại.

### Back-channel logout

Back-channel logout cho phép OP gửi Logout Token tới RP server-side. RP xác minh token theo profile, xác định session/user bị ảnh hưởng và invalidate local session tương ứng.

RP cần:

- Xác minh issuer, audience, signature, thời hạn và logout event claim.
- Kiểm tra sid/sub theo profile.
- Chống replay bằng jti/event tracking phù hợp.
- Chỉ invalidate session thuộc issuer/client tương ứng.
- Xử lý retry idempotent.

### Front-channel logout

Front-channel logout dùng browser điều hướng hoặc tải nội dung từ các RP để báo logout. Nó phụ thuộc browser, cookie policy và việc các trang có được tải hay không. Không nên coi front-channel là bảo đảm duy nhất cho logout toàn hệ thống.

## 12. SAML Single Logout

SAML 2.0 có profile Single Logout (SLO) để truyền yêu cầu/response logout giữa SP và IdP hoặc các session participant tùy triển khai.

SP cần:

- Xác minh issuer và chữ ký theo trust configuration.
- Kiểm tra destination/recipient và request correlation.
- Xác định đúng session/user dựa trên NameID/session index theo profile.
- Chống replay và xử lý request lặp idempotent.
- Invalidate local session kể cả khi participant khác không phản hồi.

SAML SLO có thể phức tạp khi nhiều SP tham gia; browser đóng, timeout hoặc một SP lỗi có thể làm luồng phân tán không hoàn tất. Mỗi SP vẫn phải hủy local session theo yêu cầu hợp lệ của chính nó.

## 13. Logout hiện tại và logout mọi thiết bị

### Logout current session

Chỉ invalidate session hiện tại và các token được gắn với phiên đó. Các thiết bị khác tiếp tục hoạt động theo policy.

### Logout all sessions

Thu hồi mọi session/token family của account trong phạm vi dịch vụ. Cần:

1. Xác minh lại user và kiểm tra quyền thực hiện.
2. Lấy danh sách session/token family từ nguồn server-side.
3. Invalidate/revoke theo batch có thể retry.
4. Tăng session/account version hoặc phát event để chặn session cũ.
5. Thu hồi refresh token và xử lý access token còn hạn.
6. Thông báo kết quả và audit số lượng credential đã xử lý.

Nếu một số service không xác nhận revoke, giao diện cần nói rõ phạm vi còn pending hoặc lỗi; không báo toàn bộ phiên đã bị thu hồi nếu mới chỉ revoke được một phần.

### Account/session version

Một mô hình có thể lưu session generation/version trên account. Khi logout all hoặc security reset, server tăng version. Session/token mang version cũ bị từ chối khi kiểm tra với trạng thái hiện tại.

Đổi lại, cách này tạo phụ thuộc vào trạng thái server-side hoặc cache đồng bộ; không thể dùng version claim mà không có nơi so sánh nó.

## 14. Logout khi request đang chạy

Logout và request nghiệp vụ có thể xảy ra gần như đồng thời:

- Request A đã xác minh session và đang xử lý giao dịch.
- Request B invalidate session do user bấm Logout.
- Request A hoàn tất sau khi logout.

Hủy session không tự động hủy mọi request đã vượt qua authentication middleware. Cần xác định semantics:

- Request bắt đầu trước logout có được hoàn tất không?
- Với thao tác giá trị cao, có cần kiểm tra session/account version ngay trước commit?
- Có thể cancel job đang chạy hay chỉ chặn request mới?
- Logout có phải chờ transaction hiện tại kết thúc không?

Với thao tác nhạy cảm, kiểm tra trạng thái session/account và authorization tại điểm commit hoặc transaction boundary. Không giả định middleware đã xác minh một lần thì trạng thái không thể thay đổi.

### Race condition và idempotency

Hai request logout đồng thời phải tạo cùng kết quả cuối: session không còn active. Invalidate nên idempotent; gọi lại không làm session sống lại hoặc tạo lỗi khiến client hiểu nhầm.

Nếu logout all chạy đồng thời với login mới, policy cần định nghĩa login mới có được phép hay phải xác thực lại sau security reset. Dùng version/generation hoặc event ordering để tránh phiên mới bị revoke nhầm hoặc phiên cũ sống lại.

## 15. Cache, browser history và back-forward cache

Sau logout, trang nhạy cảm có thể còn hiển thị do browser cache, memory state hoặc back-forward cache (BFCache). Việc trang còn nhìn thấy không có nghĩa session server vẫn hợp lệ, nhưng có thể làm lộ dữ liệu trên thiết bị dùng chung.

Kiểm soát:

- Response nhạy cảm dùng Cache-Control: no-store khi phù hợp.
- SPA xóa access token, user profile và dữ liệu nhạy cảm trong memory/store.
- Khi page được khôi phục từ BFCache, kiểm tra trạng thái session trước khi hiển thị dữ liệu nhạy cảm.
- API phải kiểm tra session/token trên mỗi request, không dựa vào UI state.
- Sau logout, điều hướng tới trang công khai không chứa dữ liệu nhạy cảm.
- Không đưa token/session ID vào URL hoặc history.

Ví dụ header:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

no-store không xóa screenshot, clipboard hoặc dữ liệu đã bị người dùng sao chép. Đây là một lớp kiểm soát cache, không thay thế authorization và session revocation.

## 16. Audit và thông báo logout

Audit event có thể ghi:

- Account/principal nội bộ.
- Session identifier dạng correlation ID không dùng để xác thực.
- Client/application và phạm vi logout.
- Thời điểm, kết quả, reason code.
- Số session/token family đã revoke hoặc còn pending.
- Nguồn kích hoạt: user, admin, incident response hoặc policy.

Không ghi:

- Cookie/session ID dạng bearer secret.
- Access token hoặc refresh token.
- Authorization header.
- Password, OTP, recovery code hoặc private key.

Thông báo logout all hoặc thu hồi phiên do quản trị viên có thể giúp user phát hiện hoạt động bất thường. Không gửi link chứa session/token hoặc thông tin có thể khôi phục credential.

## 17. Java/Spring Security: logout với server-side session

Spring Security cung cấp logout support để xử lý authentication, session và cookie. Ví dụ cấu hình:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**", "/login").permitAll()
            .anyRequest().authenticated())
        .logout(logout -> logout
            .logoutUrl("/logout")
            .invalidateHttpSession(true)
            .clearAuthentication(true)
            .deleteCookies("JSESSIONID")
            .logoutSuccessUrl("/signed-out")
            .permitAll())
        .build();
}
~~~

Spring Security mặc định hỗ trợ logout qua POST khi CSRF protection được bật. Cần giữ CSRF protection cho cookie-based application và gửi CSRF token trong form/request. Tên cookie cần khớp cấu hình servlet/container; nếu dùng Spring Session, cookie có thể tên SESSION hoặc tên custom.

### Session store dùng chung

Với Spring Session Redis/JDBC, session cần được lưu trong repository dùng chung. Spring Security logout phải invalidate session thông qua HttpSession/session repository đang được cấu hình để mọi node thấy session đã hết hiệu lực.

Kiểm tra:

- Session record thực sự bị xóa hoặc đánh dấu invalid trong store.
- Node khác không còn chấp nhận cookie cũ.
- Local cache không giữ session active quá lâu.
- Cookie được xóa với đúng name/path/domain.
- Redis/database outage có hành vi rõ ràng và có audit.

### Xóa SecurityContext

Logout handler cần clear SecurityContext và invalidate HTTP session. Không chỉ xóa một thuộc tính trong controller rồi để security context/session repository giữ principal cũ.

## 18. Java: logout service cho token và nhiều phiên

Ví dụ khung điều phối logout:

~~~java
record LogoutResult(
    boolean localSessionInvalidated,
    boolean refreshTokenRevoked,
    boolean globalLogoutRequested
) {}

@Service
class LogoutService {
    private final SessionRegistry sessions;
    private final RefreshTokenRevoker refreshTokens;
    private final AuditRecorder audit;

    LogoutService(
            SessionRegistry sessions,
            RefreshTokenRevoker refreshTokens,
            AuditRecorder audit) {
        this.sessions = sessions;
        this.refreshTokens = refreshTokens;
        this.audit = audit;
    }

    LogoutResult logoutCurrent(
            AuthenticatedPrincipal principal,
            String sessionId) {

        sessions.invalidate(principal.accountId(), sessionId);
        boolean revoked = refreshTokens.revokeForSession(
            principal.accountId(), sessionId);

        audit.recordLogout(
            principal.accountId(),
            "CURRENT_SESSION",
            revoked ? "COMPLETED" : "PARTIAL"
        );

        return new LogoutResult(true, revoked, false);
    }
}
~~~

Đây là ví dụ kiến trúc; SessionRegistry và RefreshTokenRevoker là thành phần ứng dụng cần triển khai bằng repository/provider phù hợp. Không truyền raw token vào audit. Nếu revoke token thất bại do network, trả trạng thái partial/pending và có retry/outbox phù hợp thay vì tuyên bố mọi credential đã bị thu hồi.

### Revoke all sessions

~~~java
@Transactional
void revokeAll(UUID accountId) {
    accountSecurityState.incrementSessionVersion(accountId);
    sessions.invalidateAll(accountId);
    refreshTokens.revokeAllForAccount(accountId);
    audit.recordGlobalLogout(accountId);
}
~~~

Ví dụ trên giả định các thao tác có semantics giao dịch phù hợp. Nếu session store, authorization server và audit nằm ở hệ thống khác nhau, một DB transaction không thể atomic bao trùm tất cả. Dùng outbox/saga, retry idempotent, trạng thái tiến trình và giám sát để xử lý partial failure.

## 19. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ xóa cookie browser | Cookie đã sao chép vẫn dùng được | Invalidate session phía server |
| Chỉ invalidate session nhưng không clear cookie | Browser tiếp tục gửi cookie cũ và gây request lỗi | Clear cookie đúng phạm vi |
| Dùng GET để logout | CSRF/forced logout dễ xảy ra | POST và CSRF protection |
| Invalidate trong bộ nhớ một node | Node khác vẫn chấp nhận session | Shared session store hoặc revoke propagation |
| Chỉ xóa access token ở SPA | Refresh token/session phía server vẫn tồn tại | Revoke refresh/session và clear client state |
| Coi JWT đã revoke tức thì | API có thể chấp nhận JWT tới exp | Introspection/denylist/version hoặc short lifetime |
| Logout RP nhưng không hiểu IdP session | Lần sau SSO tự đăng nhập lại | Thiết kế RP-initiated/IdP logout rõ ràng |
| Nghĩ logout IdP xóa mọi RP session | Local session có thể còn sống | Back-channel/front-channel/local revoke theo profile |
| Không xử lý request đang chạy | Action nhạy cảm có thể commit sau logout | Recheck session/version tại điểm commit |
| Revoke all không xử lý refresh token | User/attacker có thể xin token mới | Revoke token family và session |
| Audit ghi raw cookie/token | Log trở thành nguồn credential leak | Chỉ ghi correlation ID và metadata |
| Báo logout all thành công khi một service lỗi | User hiểu sai phạm vi đã thu hồi | Trả kết quả partial và retry có giám sát |
| Cache trang nhạy cảm sau logout | Dữ liệu vẫn hiện trên thiết bị dùng chung | no-store, clear client state và revalidate |

## 20. Ma trận kiểm thử logout

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Logout current session thành công | Session record phía server bị invalidate |
| Dùng lại cookie cũ sau logout | Server từ chối |
| Chỉ xóa cookie mà session store còn active | Test phát hiện cookie copy vẫn được chấp nhận; cấu hình phải sửa |
| Cookie xóa sai Path/Domain | Test phát hiện cookie còn tồn tại |
| Logout request cross-site | CSRF protection từ chối |
| Gửi GET tới logout endpoint | Không thực hiện logout thay đổi trạng thái |
| Gọi logout hai lần | Idempotent, session vẫn invalid |
| Hai app node nhận cookie cũ sau logout | Cả hai đều từ chối |
| Shared session store tạm lỗi | Hành vi theo policy; không tuyên bố revoke hoàn tất sai sự thật |
| Refresh token sau logout | Authorization server từ chối token đã revoke |
| Access JWT cũ sau logout | Bị từ chối theo chiến lược revoke/version/introspection hoặc hết hạn theo SLA |
| OIDC RP logout endpoint lỗi | Local RP session vẫn bị invalidate |
| OIDC back-channel Logout Token sai issuer/audience | RP từ chối |
| Logout Token bị replay | RP xử lý theo replay protection/idempotency |
| SAML LogoutRequest sai chữ ký/issuer | SP từ chối |
| Logout all sessions | Mọi session trong phạm vi được revoke hoặc báo partial rõ ràng |
| Login mới đồng thời với logout all | Version/order policy cho kết quả xác định |
| Request nghiệp vụ đang chạy khi logout | Hành vi commit/cancel đúng policy; action nhạy cảm recheck nếu cần |
| Browser back button sau logout | API không trả dữ liệu; UI không hiển thị state cũ theo policy |
| BFCache restore sau logout | Ứng dụng kiểm tra session trước khi hiển thị dữ liệu nhạy cảm |
| Audit logout | Có principal/scope/result, không có raw cookie/token |
| Retry sau lỗi revocation | Idempotent; cuối cùng đạt trạng thái revoke hoặc báo lỗi cần xử lý |

Kiểm thử cả local session, IdP session, refresh token và access token. Dùng credential giả lập; không sao chép session cookie hoặc token production vào test report.

## 21. Tình huống phân tích

### Tình huống A: user xóa cookie nhưng attacker vẫn đăng nhập

An bấm Logout. Ứng dụng gửi Set-Cookie với Max-Age=0 nhưng không xóa session record. Attacker có bản sao cookie từ trước.

**Phân tích:** cookie browser đã bị xóa, session server vẫn active. Invalidate session trong store trước hoặc đồng thời với việc clear cookie; kiểm tra cookie cũ bị từ chối từ mọi node.

### Tình huống B: logout một RP nhưng IdP còn phiên

An logout khỏi CRM rồi mở HR portal. HR portal tự đăng nhập lại vì IdP session vẫn còn.

**Phân tích:** local RP logout không đồng nghĩa IdP logout. Nếu yêu cầu logout toàn SSO, dùng OIDC RP-Initiated Logout/SAML SLO và cơ chế propagation phù hợp; vẫn invalidate local session của từng RP.

### Tình huống C: JWT vẫn gọi được API sau logout

SPA xóa access token khỏi memory nhưng một bản sao token vẫn còn trong log. API chấp nhận JWT đến khi exp.

**Phân tích:** xóa token ở client không thu hồi bản sao. Cần xử lý leak, revoke refresh token, giảm access token lifetime và dùng introspection/denylist/session version nếu cần thu hồi sớm.

### Tình huống D: logout all gặp partial failure

Ứng dụng đã invalidate session local nhưng authorization server timeout khi revoke refresh token. UI vẫn hiển thị “Đã đăng xuất khỏi mọi thiết bị”.

**Phân tích:** kết quả không phản ánh trạng thái thật. Cần báo partial/pending, retry idempotent qua outbox/job, giám sát và thông báo khi hoàn tất; không khẳng định toàn bộ credential đã bị thu hồi.

### Tình huống E: chuyển tiền hoàn tất sau logout

Một request chuyển tiền đã vượt qua authentication middleware. Người dùng bấm logout trong tab khác trước khi request commit.

**Phân tích:** invalidate session không tự hủy request đang chạy. Với action nhạy cảm, kiểm tra session/account version và transaction authorization tại điểm commit hoặc theo semantics đã công bố.

## 22. Quy trình thiết kế và vận hành

Trước khi phát hành logout, hãy xác định:

1. Phạm vi logout là current session, application, IdP hay all devices?
2. Credential nào đang tồn tại: cookie session, access token, refresh token, IdP session và RP local session?
3. Session store nào là nguồn có thẩm quyền; mọi node có nhìn thấy invalidation không?
4. Cookie được xóa đúng name, Path, Domain/host-only, Secure và SameSite không?
5. Logout endpoint có dùng POST và CSRF protection không?
6. Refresh token/token family có được revoke không?
7. Access token self-contained còn hiệu lực tối đa bao lâu; có introspection, denylist hoặc version check không?
8. OIDC/SAML logout propagation được hỗ trợ đến mức nào và có failure handling không?
9. Request đang chạy có thể commit sau logout không; action nào cần recheck?
10. Logout all có versioning, batch, retry, outbox và partial status không?
11. Browser cache, SPA state và BFCache được xử lý ra sao?
12. Audit có ghi đủ phạm vi/kết quả nhưng không chứa credential không?
13. Có cảnh báo khi revoke thất bại hoặc logout propagation bị trễ không?
14. Có diễn tập cookie theft, node failover, IdP outage và partial revocation không?

## 23. Ghi nhớ trọng tâm

- **Logout không chỉ là xóa cookie.** Phải invalidate session ở nơi lưu trạng thái có thẩm quyền.
- **Cookie đã sao chép vẫn dùng được nếu session server còn active.** Kiểm tra cookie cũ bị từ chối từ mọi node.
- **Logout cần xử lý từng loại credential.** Session, access token, refresh token, IdP session và RP session có vòng đời khác nhau.
- **JWT self-contained không tự mất hiệu lực khi browser logout.** Chọn short lifetime, introspection, denylist hoặc session version theo yêu cầu revoke.
- **SSO có nhiều lớp phiên.** Logout một RP không mặc định kết thúc IdP session hoặc các RP khác.
- **Logout endpoint cần CSRF protection và semantics idempotent.** Không dùng GET để thay đổi trạng thái.
- **Hệ thống phân tán cần revoke propagation.** Một node xóa session trong memory không đủ.
- **Request đang chạy có thể hoàn tất sau logout.** Với hành động nhạy cảm, kiểm tra lại trạng thái tại điểm commit.
- **Không báo logout toàn hệ thống thành công khi còn partial failure.** Theo dõi retry và trạng thái thu hồi thực tế.
- **Audit không được chứa bearer secret.** Ghi correlation ID, phạm vi, kết quả và reason code.

Logout an toàn là một quy trình thu hồi có phạm vi rõ ràng: server vô hiệu phiên, token được revoke theo khả năng của hệ thống, browser xóa cookie và trạng thái cục bộ, các RP/IdP phối hợp theo giao thức, và mọi lỗi một phần đều được quan sát. Chỉ khi credential cũ thực sự bị từ chối thì phiên mới được xem là đã kết thúc.
