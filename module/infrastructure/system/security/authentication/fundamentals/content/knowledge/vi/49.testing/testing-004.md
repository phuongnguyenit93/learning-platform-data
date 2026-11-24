# Session test: kiểm thử an toàn vòng đời phiên

> **Chương:** Testing  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào kiểm thử session: xác minh phiên được tạo, duy trì, gia hạn, hết hạn, thu hồi và truyền giữa các node đúng policy; kiểm tra cookie/browser behavior, chống session fixation và CSRF; đồng thời bảo đảm user hoặc workload không thể dùng phiên để vượt qua authorization boundary.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Xây dựng threat model và test strategy cho session-based authentication.
2. Phân biệt unit, integration, contract, browser end-to-end, security và resilience test.
3. Kiểm thử session creation, rotation, idle timeout, absolute timeout và termination.
4. Xác minh cookie flags, session fixation protection và CSRF controls.
5. Kiểm thử concurrent sessions, multi-device behavior và session limits.
6. Kiểm thử logout, administrative revoke, credential reset và revocation propagation.
7. Xác minh session store consistency, failover và behavior khi cache/database lỗi.
8. Kiểm tra authentication freshness, step-up và authorization theo resource/tenant.
9. Dùng Java/Spring Security, MockMvc và browser automation để kiểm thử session.
10. Thiết kế test data, clock, test isolation và ma trận regression an toàn.

## 2. Vì sao cần kiểm thử session riêng?

Authentication có thể xác minh credential đúng nhưng vẫn tạo hoặc quản lý session sai. Một session không được rotate sau login có thể mở đường cho session fixation. Logout có thể chỉ xóa cookie ở browser trong khi server vẫn chấp nhận session cũ. Một node có thể nhận revoke event chậm và tiếp tục chấp nhận phiên đã bị thu hồi.

Session test kiểm tra toàn bộ vòng đời:

- Session được tạo sau khi authentication và các factor bắt buộc hoàn tất.
- Session ID được thay đổi ở trust transition quan trọng.
- Cookie được phát hành với thuộc tính bảo mật đúng.
- Idle timeout và absolute timeout được thực thi.
- Session không được dùng sau logout, revoke hoặc account disable theo policy.
- Session state nhất quán giữa các instance.
- Step-up không vô tình tạo quyền lâu dài ngoài phạm vi.
- Request dùng session hợp lệ vẫn phải qua authorization.

Một test chỉ xác minh response login là 200 chưa đủ. Cần kiểm tra cookie, server-side state và request tiếp theo dùng session đó.

## 3. Threat model và test scope

Các tài sản cần bảo vệ:

- Session identifier/cookie.
- Authentication context và assurance level.
- Account, tenant và resource authorization.
- CSRF token và browser origin context.
- Session store, cache và revocation state.
- Refresh token hoặc token gắn với session.
- Device/session metadata và concurrent session policy.

Attacker có thể:

- Biết hoặc cố định session ID trước khi nạn nhân đăng nhập.
- Đánh cắp cookie qua XSS, malware hoặc endpoint compromise.
- Gửi request cross-site để browser tự đính kèm cookie.
- Replay session đã logout hoặc revoke.
- Dùng session ở node khác sau khi failover.
- Khai thác race giữa logout, refresh và request đang chạy.
- Thay đổi object ID để đọc dữ liệu user/tenant khác.
- Dựa vào clock drift hoặc cache stale để kéo dài session.

~~~mermaid
flowchart TD
    A["Authenticated browser/client"] --> B["Session creation and cookie"]
    B --> C["Session validation on each request"]
    C --> D["Authorization for action/resource"]
    D --> E["Session renewal / step-up"]
    E --> C
    C --> F["Logout / expiry / revoke"]
    F --> G["All nodes reject old session"]
    X["Attacker: fixation, theft, CSRF, replay"] -.-> B
    X -.-> C
    X -.-> D
    X -.-> F
~~~

Phạm vi kiểm thử phải bao gồm cả happy path và negative path. Test không chỉ chứng minh người dùng hợp lệ truy cập được mà còn chứng minh session cũ, sai scope, sai tenant hoặc bị thu hồi đều bị từ chối.

## 4. Phân tầng test strategy

| Loại test | Phạm vi | Ví dụ |
|---|---|---|
| Unit test | State machine, expiry calculation, policy | Session hết hạn khi vượt absolute deadline |
| Component test | Session service/repository | Revoke ghi marker và tăng security version |
| Integration test | Application + session store + security filter | Cookie login được xác minh qua request tiếp theo |
| Contract test | Browser/client và server behavior | Cookie attributes, redirect, logout contract |
| End-to-end test | Browser thật và nhiều bước | Login, step-up, access, logout |
| Security test | Attack scenarios | Fixation, CSRF, replay, cross-tenant access |
| Resilience test | Node/store/network failures | Revoke propagation sau Redis failover |
| Performance test | Load và contention | Session lookup p95/p99, concurrent login |

Unit test nhanh và phù hợp với logic deterministic. Integration test cần thiết cho filter chain, cookie serialization và shared store. Browser test cần dùng cho SameSite, Secure, redirect và behavior thực tế của cookie jar. Không cố mô phỏng mọi browser behavior chỉ bằng MockMvc.

## 5. Xác định contract của session trước khi viết test

Mỗi hệ thống cần tài liệu hóa:

- Khi nào session được tạo?
- Session ID có rotate sau login không?
- Session ID có rotate sau privilege elevation không?
- Cookie name, Domain, Path, Secure, HttpOnly và SameSite là gì?
- Idle timeout và absolute timeout là bao lâu?
- Request nào được tính là activity?
- Có sliding expiration không?
- Có giới hạn concurrent sessions không?
- Logout kết thúc một session hay tất cả session?
- Password/MFA reset ảnh hưởng những session nào?
- Revoke propagation tối đa bao lâu?
- Session có được chia sẻ giữa subdomain/application không?
- Khi store lỗi, request được xử lý thế nào?

Test cần dùng giá trị từ contract của môi trường test. Không hard-code assumption như mọi hệ thống đều cho phép nhiều session hoặc logout luôn revoke mọi thiết bị.

## 6. Session creation và authentication gate

Các kiểm thử cơ bản:

1. Anonymous request không tự tạo authenticated session.
2. Password sai không tạo session authenticated.
3. MFA bắt buộc chưa hoàn tất thì không có authenticated session đầy đủ.
4. Passkey assertion sai origin/RP ID/signature không tạo session.
5. Account disabled/locked không nhận session theo policy.
6. Login thành công tạo session mới có trạng thái và principal đúng.
7. Session không chứa password, OTP hoặc raw credential.
8. Session principal được lấy từ authentication result đáng tin, không từ request body.

Nếu framework tạo một anonymous session cho CSRF hoặc request state, phân biệt anonymous/pre-authentication session với authenticated session. Test không được nhầm hai loại.

### Authentication transaction chưa hoàn tất

Với MFA flow nhiều bước, session pre-authentication chỉ nên chứa trạng thái cần thiết để tiếp tục challenge. Nó không được có quyền truy cập như session đã hoàn tất MFA.

Kiểm tra:

- Pre-auth session chỉ gọi được challenge/verify endpoints phù hợp.
- Không truy cập API dữ liệu hoặc chức năng admin.
- Challenge hết hạn thì pre-auth state không thể tiếp tục.
- Challenge chỉ được dùng theo quy tắc one-time.
- Hoàn tất MFA tạo hoặc nâng session theo contract.
- Session ID được rotate ở ranh giới cần thiết để chống fixation.

## 7. Session fixation

Session fixation xảy ra khi attacker biết hoặc kiểm soát session identifier trước khi nạn nhân đăng nhập, sau đó lợi dụng việc ứng dụng giữ nguyên identifier sau authentication.

Test:

1. Tạo anonymous/pre-auth session.
2. Ghi nhận session ID trước login.
3. Hoàn tất login.
4. Xác minh session ID mới khác ID cũ theo contract.
5. Gửi request bằng ID cũ và xác minh không có authenticated access.
6. Kiểm tra rotation không làm mất CSRF/authentication state cần thiết.

Các transition có thể cần rotate:

- Anonymous → authenticated.
- Password-only → MFA-complete.
- User → elevated/admin session.
- Reauthentication hoặc account switch.

Không nhất thiết rotate ở mọi request. Rotation quá thường xuyên có thể gây lỗi concurrency và trải nghiệm; cần xác định đúng trust boundary.

## 8. Cookie security attributes

Với browser session cookie, kiểm tra:

| Thuộc tính | Kỳ vọng và ý nghĩa |
|---|---|
| Secure | Chỉ gửi qua HTTPS |
| HttpOnly | JavaScript không đọc trực tiếp cookie |
| SameSite | Giảm cookie gửi trong cross-site context theo policy |
| Path | Giới hạn path gửi cookie |
| Domain | Không mở rộng cookie tới subdomain không cần thiết |
| Max-Age/Expires | Phù hợp session lifetime và persistence policy |
| Prefix | Có thể dùng __Host- hoặc __Secure- theo điều kiện hỗ trợ |

Ví dụ cookie:

~~~http
Set-Cookie: __Host-SESSION=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Với __Host- cookie, cần Secure, Path=/ và không có Domain attribute. Browser sẽ áp dụng quy tắc prefix; test cần xác minh header thực tế và behavior của browser hỗ trợ.

Không ghi cookie value vào test report. Test có thể kiểm tra tên, flags và sự hiện diện của cookie mà không lưu giá trị vào artifact.

### SameSite và cross-site flow

SameSite=Lax/Strict/None có tác động khác nhau tới OAuth/OIDC callback, SAML POST binding và embedded flow. Nếu cần SameSite=None, cookie phải Secure trong browser hiện đại. Test browser thật cần xác minh callback hoạt động nhưng CSRF protection vẫn được giữ.

Không giảm SameSite hoặc bỏ CSRF token chỉ để làm một integration test pass. Sửa test client hoặc cấu hình callback theo contract.

## 9. CSRF protection

Với cookie-based authentication, browser tự gửi cookie theo request phù hợp. Attacker có thể dụ user truy cập trang khác để gửi request thay user.

Test:

- State-changing request thiếu CSRF token bị từ chối.
- Token sai hoặc token của session khác bị từ chối.
- Token hợp lệ với session hiện tại được chấp nhận.
- GET/HEAD không thực hiện side effect nghiệp vụ.
- Origin/Referer validation hoạt động theo policy.
- Login CSRF và logout CSRF được xem xét.
- JSON content type hoặc custom header không bị coi là bảo vệ duy nhất.

SameSite là defense-in-depth, không thay toàn bộ CSRF defense cho mọi ứng dụng. Bearer token gửi qua Authorization header có threat model khác cookie tự động gửi; cần test đúng client transport.

## 10. Idle timeout và absolute timeout

Test timeout phải deterministic, không dựa vào sleep dài:

- Session hoạt động trước idle deadline.
- Session bị từ chối sau idle deadline.
- Activity hợp lệ cập nhật idle deadline nếu sliding expiration được bật.
- Activity không kéo dài absolute deadline.
- Session pre-authentication có timeout riêng.
- Session step-up pending hết hạn đúng thời gian.
- Clock skew không làm session sống lâu ngoài policy.

Ví dụ:

~~~text
created_at = 10:00
idle_timeout = 15 minutes
absolute_timeout = 4 hours

activity at 10:10 -> idle deadline 10:25
activity at 10:20 -> idle deadline 10:35
no activity -> expires at 10:35

continuous activity cannot move absolute deadline beyond 14:00
~~~

Sử dụng Clock abstraction trong code để test boundary trước, đúng và sau deadline. Integration test cần kiểm tra TTL/store behavior thực tế vì unit test không chứng minh Redis/database expiry đúng.

## 11. Session renewal và rolling expiration

Rolling expiration cập nhật idle deadline khi có activity đủ điều kiện. Cần kiểm tra:

- Chỉ request hợp lệ được tính là activity.
- Health check, polling nền hoặc attacker request không giữ session sống vô hạn ngoài policy.
- Concurrent request không ghi đè deadline mới bằng timestamp cũ.
- Renewal không vượt absolute lifetime.
- Session refresh không làm mất principal, CSRF state hoặc authentication context.
- Renewal sau revoke bị từ chối.
- Cookie Max-Age/Expires được cập nhật đúng khi policy yêu cầu.

Không phải mọi endpoint đều cần kéo dài session. Một request đọc static resource hoặc telemetry có thể không nên được coi là user activity.

## 12. Logout và session termination

Logout cần kiểm thử ở cả browser và server:

- Browser xóa cookie hoặc nhận cookie hết hạn.
- Server-side session bị invalidate/revoke.
- Cookie cũ không thể dùng lại.
- Request đang chạy có behavior được định nghĩa.
- Back button không làm dữ liệu protected có thể truy cập lại từ server.
- Logout endpoint có CSRF protection khi dùng cookie.
- Logout idempotent theo contract.
- Logout không vô tình xóa session của user khác do shared cookie scope.

### Single-session và global logout

Phân biệt:

- Logout thiết bị/phiên hiện tại.
- Logout mọi phiên của user.
- Admin revoke một session cụ thể.
- Revoke toàn bộ session sau password/MFA reset.
- Revoke theo incident hoặc account disable.

Test từng semantics riêng. Không giả định một thao tác logout có hiệu lực trên mọi RP/IdP nếu federation logout không được triển khai.

## 13. Revocation và propagation trong distributed system

Trong nhiều node, session có thể được cache cục bộ. Revoke event cần tới mọi node trước khi session cũ bị chấp nhận quá giới hạn.

Test:

1. Tạo session qua node A.
2. Dùng cùng session qua node B.
3. Revoke tại node A hoặc central session service.
4. Chờ event propagation theo SLO.
5. Gửi lại request qua tất cả node.
6. Xác minh mọi node từ chối session.
7. Kiểm tra cache invalidation và store version.
8. Restart/failover một node và xác minh session cũ vẫn bị từ chối.

Đo thời gian từ revoke commit tới lần từ chối cuối cùng. Không chỉ kiểm tra node đã phát event.

### Revocation race

Kiểm thử race giữa:

- Request nghiệp vụ và logout.
- Refresh session và revoke.
- Password reset và session renewal.
- Admin revoke và node failover.
- Concurrent requests cập nhật last-access timestamp.

Định nghĩa điểm commit và linearization semantics. Với thao tác nhạy cảm, nếu quyền hoặc session state thay đổi trước commit, service có thể cần recheck hoặc optimistic version validation.

## 14. Concurrent sessions và multi-device policy

Nếu sản phẩm giới hạn số session, kiểm thử:

- Login thiết bị mới khi chưa đạt limit.
- Login vượt limit.
- Policy từ chối session mới hoặc revoke session cũ theo contract.
- Hai login đồng thời không vượt limit do race.
- Logout một thiết bị không ảnh hưởng thiết bị khác.
- Global logout kết thúc tất cả phiên.
- Session theo client type/device có metadata phù hợp.
- Device label không được dùng làm identity proof.

Quota cần được enforce atomically trong session store/service. Một test tuần tự không phát hiện race khi hai request đồng thời cùng đọc số session hiện tại.

### Device binding

Nếu session gắn với device posture hoặc key, test:

- Proof-of-possession đúng được chấp nhận.
- Key/device bị revoke thì session không tiếp tục dùng binding cũ.
- Clone cookie sang device khác bị xử lý theo policy.
- Device metadata không được tin chỉ vì client tự gửi.
- Device re-enrollment cần xác minh identity và audit.

## 15. Authentication freshness và step-up

Session có thể hợp lệ nhưng authentication đã quá cũ cho thao tác nhạy cảm.

Test:

- Endpoint thông thường chấp nhận session còn hiệu lực.
- Endpoint nhạy cảm yêu cầu auth_time trong freshness window.
- Session password-only không được coi là MFA-complete.
- Step-up thành công cập nhật assurance context theo contract.
- Step-up không thay đổi subject/tenant.
- Step-up thất bại không nâng quyền.
- Step-up grant chỉ áp dụng action/resource được chỉ định nếu policy yêu cầu.
- Session sau step-up được rotate nếu cần.
- Revoke trong lúc step-up pending khiến challenge không thể nâng session cũ.

Không suy ra assurance chỉ từ việc có nhiều factor metadata. Dùng issuer/policy semantics đã được xác định.

## 16. Authorization với session hợp lệ

Session hợp lệ chỉ xác minh principal/context. Nó không tự cho phép truy cập mọi resource.

Test object-level:

- User A đọc resource của A được phép theo policy.
- User A đọc resource của B bị từ chối.
- User thuộc tenant A không truy cập tenant B.
- Role viewer không thực hiện update/delete.
- Session admin cần step-up/freshness cho action đặc quyền.
- Account bị disable hoặc membership bị thu hồi thì quyền giảm theo SLA.
- Client không thể thay principal, role hoặc tenant bằng request body/header.

Kiểm thử IDOR/BOLA bằng cách thay resource ID, kể cả ID dạng UUID khó đoán. Test phải xác minh không có side effect và response không tiết lộ dữ liệu ngoài phạm vi.

## 17. Session store và distributed cache tests

Integration test cần kiểm tra store thực tế hoặc container tương thích:

- Create/read/update/delete session.
- TTL và expiry precision.
- Concurrent update.
- Serialization compatibility giữa phiên bản app.
- Failover và reconnect.
- Eviction behavior.
- Replication lag.
- Cache invalidation.
- Security version/revocation marker.

Test với in-memory mock không chứng minh behavior của Redis hoặc database. Dùng Testcontainers hoặc môi trường integration riêng cho semantics quan trọng.

### Failure behavior

Khi session store unavailable:

- Không tự tạo session authenticated local không được quản lý.
- Không chấp nhận session chỉ vì cache stale nếu vượt policy.
- Không bỏ qua revocation check cho action nhạy cảm.
- Trả lỗi/degraded response nhất quán.
- Circuit breaker và timeout ngăn request treo.
- Recovery sau reconnect không hồi sinh session đã revoke.

## 18. Token-backed session và refresh

Một số hệ thống dùng opaque session handle, JWT access token hoặc refresh token family. Test cần phân biệt:

- Session cookie và server-side session state.
- Access token expiry và session lifetime.
- Refresh token rotation.
- Reuse detection.
- Token revocation/introspection.
- Audience và scope.
- Logout local so với RP/IdP logout.

Test:

- Access token hết hạn bị từ chối.
- Refresh token hợp lệ được rotate đúng.
- Refresh token cũ bị reuse được phát hiện theo policy.
- Revoke session có ảnh hưởng refresh token family theo contract.
- Token audience sai không được dùng như session cho service khác.
- Clock skew không làm token được chấp nhận quá giới hạn.

Không giả định xóa browser cookie sẽ thu hồi JWT đã phát hành ở resource server. Cần test cơ chế revoke/version/introspection thực tế.

## 19. Browser end-to-end testing

Browser test cần xác minh behavior thật của cookie và redirect:

- Login form và redirect.
- Cookie flags và domain/path.
- SameSite behavior qua cross-site callback.
- Session ID rotation.
- CSRF token lifecycle.
- Logout và cookie deletion.
- Multi-tab behavior.
- Concurrent request khi session renew/revoke.
- Back button và cached page behavior.

Dùng test account và environment riêng. Không lưu cookie jar hoặc HAR chứa token/session vào artifact công khai. Nếu test framework tạo video/screenshot/network trace, phải kiểm tra redaction và access policy.

Browser automation không chứng minh mọi browser/version hoạt động giống nhau. Chọn browser matrix dựa trên support policy và các flow có cross-site behavior.

## 20. Test clock và deterministic expiry

Không dùng sleep dài trong unit test để chờ session hết hạn. Thay vào đó:

- Inject Clock vào session service.
- Dùng fixed/mutable clock để đi qua deadline.
- Kiểm tra instant ngay trước deadline.
- Kiểm tra đúng tại deadline theo semantics đã định.
- Kiểm tra ngay sau deadline.
- Tách wall clock và monotonic duration clock.
- Integration test kiểm tra TTL thật của store.

Ví dụ:

~~~java
class SessionExpiryPolicy {
    private final Clock clock;
    private final Duration idleTimeout;
    private final Duration absoluteTimeout;

    SessionExpiryPolicy(
            Clock clock,
            Duration idleTimeout,
            Duration absoluteTimeout) {
        this.clock = clock;
        this.idleTimeout = idleTimeout;
        this.absoluteTimeout = absoluteTimeout;
    }

    boolean isExpired(Instant createdAt, Instant lastActivityAt) {
        Instant now = clock.instant();
        return !now.isBefore(createdAt.plus(absoluteTimeout))
            || !now.isBefore(lastActivityAt.plus(idleTimeout));
    }
}
~~~

Ví dụ dùng quy tắc deadline inclusive: tại thời điểm bằng deadline, session đã hết hạn. Nếu hệ thống chọn semantics khác, điều chỉnh code và boundary test đồng bộ.

## 21. Java/Spring: kiểm thử login và session bằng MockMvc

Ví dụ minh họa kiểm tra session fixation và cookie contract trong Spring Security. Endpoint, cookie name và cấu hình cần khớp ứng dụng thực tế.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SessionLoginIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void loginRotatesSessionIdentifier() throws Exception {
        MockHttpSession beforeLogin = new MockHttpSession();
        String oldId = beforeLogin.getId();

        MvcResult result = mvc.perform(post("/login")
                .session(beforeLogin)
                .param("username", "test-user")
                .param("password", "test-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession afterLogin = result.getRequest().getSession(false);
        assertThat(afterLogin).isNotNull();
        assertThat(afterLogin.getId()).isNotEqualTo(oldId);
    }
}
~~~

Đây là khung minh họa; form login, CSRF và session strategy có thể cần thiết lập thêm trong test. Với Spring Security, session fixation protection có thể đổi session ID hoặc tạo session mới tùy container/configuration. Test nên xác minh behavior contract chứ không giả định implementation cụ thể.

### Kiểm tra cookie flags

~~~java
@Test
void sessionCookieHasSecureAttributes() throws Exception {
    MvcResult result = mvc.perform(post("/login")
            .with(csrf())
            .param("username", "test-user")
            .param("password", "test-password"))
        .andExpect(status().is3xxRedirection())
        .andReturn();

    String setCookie = result.getResponse().getHeader("Set-Cookie");
    assertThat(setCookie).contains("Secure");
    assertThat(setCookie).contains("HttpOnly");
    assertThat(setCookie).contains("SameSite=Lax");
    assertThat(setCookie).contains("Path=/");
}
~~~

Trong môi trường test HTTP, Secure cookie có thể không được browser gửi lại. Dùng HTTPS test setup hoặc browser test phù hợp. Không bỏ Secure chỉ để MockMvc thuận tiện.

## 22. Java/Spring: kiểm thử logout và revoke

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SessionLogoutIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void oldSessionCannotAccessProtectedResourceAfterLogout()
            throws Exception {
        MockHttpSession session = authenticatedSessionFor("test-user");

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/api/profile").session(session))
            .andExpect(status().isUnauthorized());
    }
}
~~~

authenticatedSessionFor là helper test cần tạo session qua flow authentication thực hoặc fixture được kiểm soát. Nếu chỉ thêm SecurityContext giả vào session, test phải xác minh session repository và logout handler thực sự dùng đúng key/configuration.

Với distributed session, chạy test qua nhiều application instance và shared store; một MockMvc instance đơn lẻ không kiểm chứng propagation.

## 23. Java/Spring: kiểm thử CSRF và authorization

~~~java
@Test
void stateChangingRequestRequiresCsrf() throws Exception {
    MockHttpSession session = authenticatedSessionFor("test-user");

    mvc.perform(post("/api/profile/email")
            .session(session)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"email\":\"new@example.test\"}"))
        .andExpect(status().isForbidden());
}

@Test
void userCannotReadAnotherUsersResource() throws Exception {
    MockHttpSession session = authenticatedSessionFor("user-a");

    mvc.perform(get("/api/users/user-b/profile").session(session))
        .andExpect(status().isForbidden());
}
~~~

Status 403/404 phụ thuộc API contract và cách tránh resource enumeration. Ngoài response, kiểm tra database không bị thay đổi và không có side effect. CSRF test cần chạy với security filter chain thật.

## 24. Test data và isolation

Session test dễ flaky nếu dùng chung account, cookie hoặc store:

- Mỗi test tạo user/session riêng hoặc namespace riêng.
- Cleanup session sau test.
- Không dùng production credential.
- Không chia sẻ static session ID.
- Reset test clock và store state.
- Tách test chạy song song theo tenant/namespace.
- Dùng deterministic key/fixture chỉ trong test environment.
- Không log cookie/token trong failure output.
- Mask secret trong screenshots, HAR và CI artifacts.

Test isolation cần kiểm tra cả distributed store. Một test logout global không được làm thất bại test khác vì dùng chung account.

## 25. Performance và concurrency testing

Session validation thường nằm trên hot path của API. Kiểm thử:

- Throughput lookup ở tải bình thường và peak.
- p95/p99 latency.
- Concurrent login và session creation.
- Concurrent renewal/update.
- Concurrent logout và business request.
- Revocation event fan-out.
- Session store saturation và connection pool.
- Expired session cleanup throughput.
- Memory/storage growth.

Load test không dùng credential thật hoặc tạo hàng triệu account thật. Dùng synthetic identity, test key và giới hạn blast radius.

Kiểm tra retry không tạo duplicate session hoặc token family. Nếu session creation là side effect có idempotency contract, test duplicate request và timeout sau commit.

## 26. Security regression cases

Một regression suite tối thiểu nên bao gồm:

- Session ID không giữ nguyên qua login.
- Cookie flags không bị mất sau deploy.
- CSRF protection không bị disable.
- Logout invalidates server-side state.
- Revoked session bị từ chối trên mọi node.
- Idle/absolute timeout không bị kéo dài ngoài policy.
- Account disable/password reset có hiệu lực đúng SLA.
- Step-up không nâng session sai subject hoặc tenant.
- Object-level authorization luôn được kiểm tra.
- Session không được tạo trước MFA bắt buộc.
- Session store outage không fail open.
- Browser back/cache không làm lộ dữ liệu protected.

Mỗi security regression nên có test tái hiện lỗi và assertion cho cả response lẫn state/side effect.

## 27. Ma trận kiểm thử session

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Anonymous truy cập protected endpoint | Bị yêu cầu authentication |
| Login password hợp lệ | Session authenticated được tạo |
| Password sai | Không tạo authenticated session |
| MFA bắt buộc chưa hoàn tất | Chỉ pre-auth state, không có quyền protected |
| MFA hoàn tất | Session đạt assurance theo policy |
| Passkey origin/RP ID sai | Không tạo session |
| Login sau anonymous session | Session ID rotate |
| Dùng session ID cũ sau login | Không có authenticated access |
| Cookie Secure/HttpOnly/SameSite | Header và browser behavior đúng contract |
| Cross-site state-changing request thiếu CSRF | Bị từ chối |
| CSRF token của session khác | Bị từ chối |
| Activity trước idle deadline | Session còn hiệu lực |
| Activity sau idle deadline | Session bị từ chối |
| Activity liên tục qua absolute deadline | Session vẫn hết hạn |
| Renewal sau revoke | Bị từ chối |
| Logout hiện tại | Cookie và server-side state bị invalidate |
| Replay cookie sau logout | Bị từ chối |
| Global logout | Mọi session theo scope bị revoke |
| Password reset | Session cũ bị xử lý theo policy |
| Account disable | Session không tiếp tục được chấp nhận |
| Concurrent login vượt session limit | Policy xử lý atomically |
| Logout một device | Session device khác giữ trạng thái theo contract |
| Revoke trên node A, request qua node B | Node B từ chối trong revoke SLO |
| Node restart sau revoke | Không hồi sinh session cũ |
| Session store unavailable | Fail/degraded theo policy, không fail open |
| Stale replica promoted | Revocation/security version được reconcile |
| JWT hết hạn | Request bị từ chối |
| Refresh token reuse | Detection/revocation theo policy |
| Token audience sai | Bị từ chối |
| Session hợp lệ nhưng object thuộc user khác | Authorization từ chối |
| Session hợp lệ nhưng tenant khác | Authorization từ chối |
| Step-up grant sai resource/action | Không được dùng cho action khác |
| Browser back sau logout | Protected data không được tải lại từ server |
| Session ID xuất hiện trong metric/log | Secret/identifier scan phát hiện |
| Concurrent renewal và logout | Kết quả tuân theo ordering/commit policy |
| Clock boundary | Expiry chính xác trước/tại/sau deadline |
| Cookie SameSite trong OIDC/SAML callback | Callback hoạt động và CSRF controls vẫn có hiệu lực |
| Test chạy song song | Session và store state không rò giữa test |

Ma trận cần được điều chỉnh theo contract cụ thể, nhưng các nhóm fixation, cookie, CSRF, timeout, revoke, distributed consistency và authorization không nên bị bỏ qua.

## 28. Tình huống phân tích

### Tình huống A: logout chỉ xóa cookie

Browser nhận response logout và xóa cookie. Attacker vẫn giữ bản sao cookie cũ và request tới API thành công.

**Phân tích:** Logout chưa invalidate server-side session. Test cần replay cookie cũ sau logout và xác minh bị từ chối trên mọi node.

### Tình huống B: login giữ nguyên session ID

Ứng dụng tạo anonymous session trước login và tiếp tục dùng ID đó sau khi password/MFA thành công.

**Phân tích:** Session fixation. Bổ sung session fixation protection và test ID rotation ở các trust transition.

### Tình huống C: session không hết hạn khi user hoạt động liên tục

Idle timeout được reset mỗi request nhưng absolute timeout không được thực thi.

**Phân tích:** Sliding expiration đã vô tình biến thành session lifetime vô hạn. Test clock phải xác minh absolute deadline không dịch chuyển.

### Tình huống D: revoke không lan tới node khác

Node A ghi revoke nhưng node B giữ cache cũ và tiếp tục chấp nhận session.

**Phân tích:** Cần shared revocation state, event propagation, cache invalidation và test failover/restart. Đo revoke latency tới lần từ chối cuối cùng.

### Tình huống E: CSRF bị tắt để test login pass

Một integration test bỏ CSRF filter vì request POST bị 403.

**Phân tích:** Test đã né security control. Dùng CSRF token/helper phù hợp và giữ filter chain thật trong integration test.

### Tình huống F: user A đọc được resource của user B

Session của A hợp lệ và API trả resource theo ID mà không kiểm tra owner.

**Phân tích:** Authentication pass nhưng object-level authorization fail. Thêm test đổi resource ID và xác minh không có dữ liệu/side effect ngoài quyền.

## 29. Quy trình xây dựng session test suite

Trước khi phát hành session implementation, hãy xác định:

1. Session contract, state machine và source of truth là gì?
2. Pre-authentication và authenticated session được phân biệt ra sao?
3. Session ID rotate ở trust transition nào?
4. Cookie attributes và browser matrix nào cần kiểm tra?
5. CSRF protection được kiểm thử trên state-changing request thế nào?
6. Idle, absolute và pre-auth timeout có test clock deterministic không?
7. Logout, single-session revoke và global revoke có semantics rõ không?
8. Concurrent session limit được enforce nguyên tử không?
9. Revocation propagation có test multi-node và failover không?
10. Session store outage/stale replica có fail safe không?
11. Authentication freshness và step-up được ràng buộc với action/resource không?
12. Authorization object/tenant có negative test không?
13. Cookie/token/session identifier có bị ghi vào test artifacts không?
14. Test isolation có an toàn khi chạy parallel không?
15. Performance/chaos test có blast radius và rollback plan không?
16. Regression suite có được chạy trong CI trước release không?

## 30. Ghi nhớ trọng tâm

- **Kiểm thử session phải đi qua toàn bộ lifecycle.** Tạo, rotate, sử dụng, renew, expire, logout và revoke.
- **Login success chưa chứng minh session an toàn.** Kiểm tra cookie, server-side state và request tiếp theo.
- **Session fixation, CSRF và cookie flags là nhóm test thiết yếu.**
- **Idle timeout không thay absolute timeout.** Activity không được kéo dài phiên vô hạn.
- **Logout phải vô hiệu hóa session theo server-side contract.** Xóa cookie ở browser chưa đủ.
- **Distributed revocation cần test trên nhiều node và sau failover.** Đo thời gian tới khi node cuối cùng từ chối phiên cũ.
- **Session hợp lệ vẫn cần authorization.** Test IDOR/BOLA, tenant isolation và action-specific permission.
- **Test clock và test store đúng cách.** Unit mock không thay integration test Redis/database và browser thật.
- **Không để test artifact chứa cookie/token.** Screenshots, HAR, trace và CI log cũng là dữ liệu cần bảo vệ.
- **Một test chỉ đạt khi security outcome đúng.** Hệ thống trả response thành công nhưng cho phép session cũ hoặc truy cập sai tenant là test thất bại.

Session test tốt chứng minh phiên được tạo đúng sau authentication, chỉ tồn tại trong thời hạn và phạm vi được phép, có thể thu hồi nhất quán trên toàn hệ thống, và không biến một principal hợp lệ thành quyền truy cập vượt mức. Kết hợp unit, integration, browser, security và resilience test giúp phát hiện lỗi ở cả protocol, framework, browser và distributed state.
