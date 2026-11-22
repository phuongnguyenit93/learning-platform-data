# Kiểm chứng khóa tài khoản, đổi mật khẩu và đăng xuất trên nhiều phiên

## 1. Mục tiêu và bối cảnh

Người dùng có thể đăng nhập cùng lúc trên laptop, điện thoại, hai browser hoặc nhiều application nodes. Khi tài khoản bị **khóa**, người dùng **đổi mật khẩu**, hoặc yêu cầu **đăng xuất khỏi tất cả thiết bị**, hệ thống phải chứng minh những bằng chứng xác thực cũ không còn được chấp nhận theo chính sách. Một dòng `account.locked = true` hoặc một HTTP response thành công không đủ.

Bài thực hành dùng **Spring Security Servlet**, đặt trong ngữ cảnh Spring Boot 3.x/Spring Security 6.x, với ba phiên:

- **A**: Alice đăng nhập trên browser 1.
- **B**: Alice đăng nhập trên browser 2.
- **C**: Bob đăng nhập trên browser 3 để kiểm tra không thu hồi nhầm tài khoản khác.

Sau đó Alice mở khóa và đăng nhập lại bằng **D**; đổi mật khẩu và đăng nhập lại bằng **E**, **F**. Ta kiểm chứng **logout một phiên E** vẫn giữ F; **logout all** thì F cũng bị từ chối.

Mục tiêu:

1. Hiểu vì sao các kiểm tra `UserDetails.isAccountNonLocked()` lúc login không đồng nghĩa session đang tồn tại bị khóa ngay.
2. Xây tiêu chí kiểm thử cho login mới, session cũ, password hash, logout current và logout all.
3. Dùng session epoch/version và Spring Session để thực thi thu hồi nhiều phiên, nhiều nodes.
4. Phân biệt `SessionRegistry.expireNow()` với xóa server-side session.
5. Kiểm thử với `MockMvc`, Spring Session/Redis và HTTP cookie jars thật.
6. Không quên refresh token, JWT access token, remember-me, MFA proof và phiên IdP khi yêu cầu nghiệp vụ đòi thu hồi rộng hơn.
7. Thực hành một chương trình **Java 17 chạy độc lập** mô phỏng đầy đủ state transitions cùng stdout chính xác.

**Phạm vi chính sách minh họa:** khóa account sẽ **chặn cả login mới và mọi session cũ**. Đổi mật khẩu thành công sẽ **buộc mọi phiên cũ, kể cả phiên thực hiện thay đổi, đăng nhập lại**. Những hệ thống chỉ khóa login mới hoặc giữ phiên vừa re-auth phải công bố chính sách khác và viết test tương ứng.

## 2. Những trạng thái cần phân biệt

| Đối tượng | Trạng thái | Điều kiện cho phép |
|---|---|---|
| Account | `ACTIVE`, `LOCKED`, `DISABLED`, `SUSPENDED` | Không đủ chỉ nhìn password; phải theo policy đang hiệu lực. |
| Password | Hash hiện hành, credential version | Password mới phải được verify với hash mới, password cũ bị từ chối khi login. |
| Browser session | Session ID, principal, issued epoch | Session còn tồn tại, account active, issued epoch trùng current epoch. |
| Remember-me | Token/series/cookie | Không bị revoke và owner còn được phép. |
| OAuth refresh token | Authorization grant/token family | Grant active, account active, token chưa bị revoke/expired. |
| Access JWT | Chữ ký, `iss`, `aud`, `exp`, scopes, version | Hợp lệ về crypto **và** thỏa revoke strategy hiện tại. |
| MFA proof | Factor, challenge, verifiedAt, purpose | Factor còn hợp lệ, proof chưa bị revoke, đủ freshness. |
| OIDC/SSO | Local RP session và IdP session | Phải xử lý từng loại; logout RP không mặc định logout IdP. |

**Credential đã được cấp trước đó có thể sống dài hơn password.** Cập nhật mật khẩu trong DB không tự làm mất hiệu lực bearer JWT, refresh grants, API keys hoặc remember-me cookies.

Thao tác **logout current** chỉ có phạm vi một phiên local nếu không nói khác. Thao tác **logout all devices** phải định nghĩa rõ có bao gồm OIDC/IdP, OAuth2 grants, mobile refresh tokens và trusted devices hay không, thay vì ghi một nhãn UI mơ hồ.

## 3. Ma trận hành vi trước khi viết code

| Thời điểm | A (Alice) | B (Alice) | C (Bob) | Login Alice |
|---|---|---|---|---|
| Ban đầu | Allow | Allow | Allow | Allow với password đúng |
| Sau khóa Alice | Deny | Deny | Allow | Deny dù password đúng |
| Sau mở khóa Alice | Deny, không hồi sinh | Deny, không hồi sinh | Allow | Allow, cấp session D mới |
| Sau đổi password | D và mọi session cũ deny | Mọi session cũ deny | Allow | Old password fail, new password success |
| Sau logout current E | E deny | F cùng account allow | Allow | Có thể login nếu account active |
| Sau logout all Alice | Mọi Alice session deny | F deny | Allow | Có thể login lại bằng credential mới |

Một thay đổi nên được coi là thành công khi **request kế tiếp sử dụng cookie/session ID cũ bị chặn**, không chỉ khi mutation API trả `200` hoặc UI hiện “Đã đăng xuất”.

Các assertion tối thiểu:

- Phiên A và B là **hai session IDs khác nhau**, không phải cùng một object dùng lại.
- Bob không bị logout vì principal lookup sai hoặc cleanup quét quá rộng.
- Unlock không phục hồi A/B hoặc token ở security epoch trước.
- Khi password change thất bại vì current password sai, **không** đổi hash/epoch hoặc revoke session ngoài ý định.
- Event cleanup bị trễ không tạo khoảng cho stale session tiếp tục truy cập ngoài SLA.

## 4. Cơ chế Spring Security liên quan

Trong Servlet stack:

~~~text
Browser Cookie JSESSIONID/SESSION
        |
        v
Servlet FilterChain / Spring Security FilterChainProxy
        |
        v
SecurityContextRepository loads Authentication from session
        |
        +-- AuthorizationFilter / method security
        |
        +-- application business method
~~~

Khi login bằng form:

~~~text
POST /login
    -> UsernamePasswordAuthenticationFilter
    -> AuthenticationManager / ProviderManager
    -> DaoAuthenticationProvider / UserDetailsService
    -> PasswordEncoder matches password
    -> user account status checks
    -> SecurityContext persisted in HttpSession
~~~

`UserDetails.isAccountNonLocked()` và `isEnabled()` được dùng trong quá trình xác thực ở provider phù hợp. **Request có session đã xác thực có thể chỉ khôi phục `Authentication` từ `SecurityContextRepository`, không chạy lại password provider.** Vì vậy set `locked=true` chưa chắc chặn session A/B đang có.

Thêm vào đó, `SecurityContextHolder.clearContext()` chỉ clear context của execution hiện tại; nó **không tự xóa** các session từ thiết bị khác hoặc refresh/access tokens. Cần session repository/index/epoch gate riêng.

## 5. Thiết kế state nguồn và monotonic epoch

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE app_account (
  user_id           VARCHAR(80) PRIMARY KEY,
  username          VARCHAR(120) UNIQUE NOT NULL,
  password_hash     VARCHAR(255) NOT NULL,
  status            VARCHAR(24) NOT NULL,
  security_epoch    BIGINT NOT NULL DEFAULT 1,
  authz_version     BIGINT NOT NULL DEFAULT 1,
  updated_at        TIMESTAMPTZ NOT NULL
);

CREATE TABLE security_outbox (
  event_id          VARCHAR(80) PRIMARY KEY,
  subject_user_id   VARCHAR(80) NOT NULL,
  event_type        VARCHAR(50) NOT NULL,
  target_epoch      BIGINT NOT NULL,
  actor_user_id     VARCHAR(80),
  created_at        TIMESTAMPTZ NOT NULL
);
~~~

`user_id` là định danh bất biến, không thay theo email hoặc username. `password_hash` dùng `PasswordEncoder` có thuật toán phù hợp (ví dụ BCrypt/Argon2). `security_epoch` tăng khi cần thu hồi tất cả session/proofs cũ; `authz_version` có thể tăng riêng khi role/tenant permissions thay đổi.

Ví dụ:

~~~text
Account Alice: status=ACTIVE, epoch=7
Session A: issuedEpoch=7 -> accepted
Session B: issuedEpoch=7 -> accepted

Admin locks Alice:
  update status=LOCKED
  update epoch=8
  commit

Next request:
  A/B issuedEpoch=7 != current 8 -> denied
  status=LOCKED -> denied

Admin unlocks:
  update status=ACTIVE
  epoch remains >=8 (can increase again)
  A/B epoch=7 -> denied
  new D issuedEpoch=current -> accepted
~~~

**Epoch tăng trong DB không có hiệu lực nếu enforcement point không kiểm nó.** Nếu một node chỉ dùng session SecurityContext snapshot và cache stale vô thời hạn, token/session cũ vẫn có thể được nhận.

## 6. Khóa account phải commit trước khi báo thành công

Luồng quản trị phù hợp:

~~~text
Security admin -> POST /admin/users/{id}/lock
   |
   +-- authenticate actor and authorize by tenant
   +-- transactional account update:
   |       ACTIVE -> LOCKED
   |       securityEpoch++
   |       append security_outbox event
   +-- commit
   +-- request gate sees locked status / newer epoch
   +-- cleanup sessions/grants asynchronously with retry
   +-- audit + notification
~~~

Snippet Spring service **cần domain types do dự án triển khai**:

~~~java
@Transactional
public long lockAccount(String stableUserId, String actorId) {
    AccountEntity account =
            repository.findByIdForUpdate(stableUserId)
                    .orElseThrow(AccountNotFoundException::new);

    if (!account.isLocked()) {
        account.setLocked(true);
        account.setSecurityEpoch(account.getSecurityEpoch() + 1);
        outbox.saveLocked(account.getId(),
                account.getSecurityEpoch(), actorId);
    }
    return account.getSecurityEpoch();
}
~~~

Đây là **integration snippet**, chưa phải ứng dụng có thể chạy chỉ bằng `javac`. `findByIdForUpdate` cần transaction/pessimistic lock hoặc cơ chế optimistic versioning cụ thể; `outbox` phải được commit cùng thay đổi account. Hạn chế race và duplicate messages bằng event ID/version. Không cho client tự chọn tenant/subject ngoài quyền của admin.

**Điểm chứng minh:** ngay sau commit, thử login mới với password đúng của account đã locked phải thất bại. Đồng thời cookie A/B trước đó cũng phải bị từ chối nếu chính sách lock là “khóa truy cập ngay”.

## 7. Đổi mật khẩu: kiểm tra old credential và vô hiệu phiên cũ

Đổi password tự phục vụ yêu cầu:

1. Có authenticated principal hiện hành, ánh xạ sang internal ID từ nguồn đáng tin.
2. Kiểm CSRF với session-backed POST và recent re-auth/MFA nếu policy.
3. Xác minh current password bằng `passwordEncoder.matches(...)`.
4. Kiểm password policy cho new password (độ dài, blacklist/breached password, history theo chính sách).
5. Transaction: lưu `passwordEncoder.encode(newPassword)`, tăng `securityEpoch`, thêm outbox event.
6. Sau commit, invalidate current session/clear SecurityContext; cleanup other sessions, remember-me, refresh grants/proofs theo phạm vi.
7. Gửi thông báo an toàn, không đưa raw password vào audit/log.

Ví dụ:

~~~java
@Transactional
public long changePassword(
        String stableUserId, String oldPassword, String newPassword) {

    AccountEntity a = repository.findByIdForUpdate(stableUserId)
            .orElseThrow(AccountNotFoundException::new);

    if (!a.isActive() || a.isLocked()) {
        throw new AccountPolicyException();
    }
    if (!passwordEncoder.matches(oldPassword, a.getPasswordHash())) {
        throw new BadCredentialsException("Credential not accepted");
    }
    passwordPolicy.validate(newPassword);

    a.setPasswordHash(passwordEncoder.encode(newPassword));
    a.setSecurityEpoch(a.getSecurityEpoch() + 1);
    outbox.savePasswordChanged(a.getId(), a.getSecurityEpoch());
    return a.getSecurityEpoch();
}
~~~

Các field/types ở trên thuộc ứng dụng, không phải classes có sẵn của Spring Security. **Không nhận `stableUserId` từ request body** để cho người dùng đổi password của người khác; sử dụng authenticated internal principal. Password reset vì quên mật khẩu là workflow khác với recovery token single-use/hạn dùng và security checks riêng.

Test phải xác nhận: password hash trước/sau khác; `matches(newPassword, storedHash)` true; mật khẩu cũ fail ở login mới; **hai session A/B cũ bị từ chối**; password change thất bại vì old password sai **không** đổi epoch/hash.

## 8. Logout một phiên khác logout all

Spring Security Servlet có `logout()` và các logout handlers. Handler thông thường xóa `SecurityContext` và invalidate `HttpSession` hiện tại. Khi CSRF đang bật, **POST `/logout`** là hành vi mặc định phù hợp.

~~~java
http.authorizeHttpRequests(a -> a
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated())
    .formLogin(Customizer.withDefaults())
    .logout(logout -> logout
        .logoutUrl("/logout")
        .invalidateHttpSession(true)
        .clearAuthentication(true));
~~~

Đây là snippet cấu hình trong `SecurityFilterChain` đã có `HttpSecurity`/`Customizer`, không phải standalone. Không disable CSRF toàn hệ thống chỉ để hỗ trợ logout qua GET. Nếu logout dùng form/SPA, gửi CSRF token theo configured repository.

**Logout current:**

~~~text
POST /logout with session A + CSRF-A
  -> delete/invalidate A server-side
  -> A cookie cũ không đăng nhập lại được
  -> B cùng user vẫn active
  -> C khác user vẫn active
~~~

**Logout all:**

~~~text
POST /sessions/logout-all with Alice's authenticated context
  -> require recent assurance / step-up if sensitive
  -> bump Alice.securityEpoch
  -> delete/expire Alice sessions
  -> A/B/D/F all denied
  -> Bob session C remains active
~~~

Một câu lệnh `SecurityContextHolder.clearContext()` chỉ xử lý current context, không phải all devices. Chỉ xóa cookie ở browser cũng không đủ nếu cookie đã bị copy.

## 9. Spring Session và `FindByIndexNameSessionRepository`

Spring Session Redis/JDBC có thể quản lý session tập trung và hỗ trợ index theo principal. Giao diện `FindByIndexNameSessionRepository<S extends Session>` cung cấp `findByPrincipalName(...)`. Khi tìm được session IDs, dùng `deleteById(...)`:

~~~java
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

public final class AllSessionsRevoker<S extends Session> {
    private final FindByIndexNameSessionRepository<S> sessions;

    public AllSessionsRevoker(
            FindByIndexNameSessionRepository<S> sessions) {
        this.sessions = sessions;
    }

    public int revoke(String indexedPrincipal) {
        Map<String, S> found =
                sessions.findByPrincipalName(indexedPrincipal);
        found.keySet().forEach(sessions::deleteById);
        return found.size();
    }
}
~~~

Đây là **mã tích hợp** với Spring Session. Spring Session docs lưu ý principal name index phải được populate; một số tích hợp tự index tên người dùng từ Spring Security, nhưng với custom principals phải kiểm. Tên index phải **trùng giá trị thực sự đã ghi**, lý tưởng là immutable user ID và tenant namespace rõ ràng. Không giả định gọi `findByPrincipalName("usr-1001")` sẽ tìm được khi app đang index `"alice@example.test"`.

Lỗ hổng có thể gặp:

- Session tạo đồng thời ngay trước/sau lần quét index bị bỏ sót.
- Một node giữ session cache cũ và vẫn cho phép truy cập.
- Index theo email bị đổi, hoặc hai tenants dùng username giống nhau.
- Redis unavailable khiến cleanup bị trễ.
- Delete session không đồng nghĩa revoke refresh JWT/API key.

Vì vậy, **security epoch trên request path + physical session cleanup** bổ trợ cho nhau. Nếu cleanup thất bại, epoch vẫn chặn theo SLA; outbox/retry/reconciliation sẽ dọn state.

## 10. `SessionRegistry.expireNow()` không phải delete ngay mọi node

Spring Security `SessionRegistry` và `SessionInformation` dùng cho quản lý concurrent sessions. Có thể gọi:

~~~java
List<SessionInformation> active =
        sessionRegistry.getAllSessions(principal, false);
for (SessionInformation s : active) {
    s.expireNow();
}
~~~

Hành vi: đánh dấu sessions expired để cơ chế như `ConcurrentSessionFilter` (khi đã được cấu hình) nhận biết trên request tiếp theo, rồi xử lý expiration. **Không mặc nhiên hủy HttpSession đồng bộ trên toàn bộ cluster.** Nếu dùng `SessionRegistryImpl` local ở một node, nó có thể không nhìn thấy session của browser B ở node khác. Tài liệu Spring Security cũng khuyến cáo kiểm `equals/hashCode` của custom UserDetails khi session registry index dựa trên principal equality.

Test phải xác nhận **filter thực sự hoạt động**, request tiếp theo bị chặn, và cross-node state nhất quán; không chỉ kiểm `isExpired() == true` trong registry object.

`maximumSessions(1)` là concurrency-control policy, không thay cho logout-all endpoint. Một user đã đăng nhập từ trước có thể có remember-me/refresh token/JWT nằm ngoài session registry.

## 11. Enforcement bằng session security epoch

Để ngăn SecurityContext stale, mỗi session lưu `LOGIN_EPOCH` do server cấp khi authentication thành công:

~~~text
Session A: principal=usr-1001, LOGIN_EPOCH=11
Account:   userId=usr-1001, active=true, securityEpoch=11
GET /me -> allow

Admin locks:
Account: locked=true, securityEpoch=12
GET /me with A -> deny
~~~

Một Servlet `OncePerRequestFilter` **minh họa tích hợp**, cho session-backed authentication:

~~~java
import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class SessionEpochGuardFilter extends OncePerRequestFilter {
    public static final String LOGIN_EPOCH = "LOGIN_EPOCH";
    private final AccountStateLookup states;

    public SessionEpochGuardFilter(AccountStateLookup states) {
        this.states = states;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication a =
                SecurityContextHolder.getContext().getAuthentication();

        if (a == null || !a.isAuthenticated()
                || a instanceof AnonymousAuthenticationToken) {
            chain.doFilter(request, response);
            return;
        }

        String userId = states.resolveVerifiedInternalId(a);
        HttpSession session = request.getSession(false);
        Object issued = session == null ? null :
                session.getAttribute(LOGIN_EPOCH);
        AccountStateLookup.State current =
                states.loadAuthoritative(userId);

        boolean accepted = current != null
                && current.active()
                && issued instanceof Long
                && ((Long) issued) == current.epoch();

        if (!accepted) {
            SecurityContextHolder.clearContext();
            if (session != null) {
                session.invalidate();
            }
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }
        chain.doFilter(request, response);
    }
}
~~~

Contract phụ trợ phải do dự án triển khai:

~~~java
interface AccountStateLookup {
    record State(boolean active, long epoch) {}
    String resolveVerifiedInternalId(Authentication authentication);
    State loadAuthoritative(String stableUserId);
}
~~~

**Đây không phải Spring Boot app có thể chạy chỉ bằng `javac`.** Cần source lookup/transaction, authentication setup, imports, bean wiring và error handling của dự án thật. Filter phải chạy sau khi security context đã được load và trước quyền truy cập; có thể đăng ký bằng:

~~~java
http.addFilterAfter(
        new SessionEpochGuardFilter(states),
        SecurityContextHolderFilter.class);
~~~

`SecurityContextHolderFilter` thuộc package `org.springframework.security.web.context`, còn bean `states` do ứng dụng cung cấp. Với nhiều `SecurityFilterChain`, phải áp guard trên các chains dùng session; login OIDC/remember-me và custom login cần cấp epoch đúng path.

**Giới hạn cực kỳ quan trọng:** filter trên **chỉ dành cho session-backed requests**. Bearer JWT stateless không có `HttpSession` sẽ bị từ chối theo logic này; dùng một **token-specific epoch/status gate** riêng cho resource server, không copy filter nguyên xi vào JWT API.

## 12. Gắn issued epoch ở lần login thành công

Sau khi provider xác thực thành công và account status vẫn active, success handler có thể ghi epoch vào session:

~~~java
http.formLogin(form -> form.successHandler(
        (request, response, authentication) -> {
    String userId =
            states.resolveVerifiedInternalId(authentication);
    AccountStateLookup.State current =
            states.loadAuthoritative(userId);

    if (current == null || !current.active()) {
        throw new IllegalStateException(
                "Account state changed during login");
    }

    request.getSession(true).setAttribute(
            SessionEpochGuardFilter.LOGIN_EPOCH,
            current.epoch());

    response.sendRedirect("/dashboard");
}));
~~~

Đây là **integration snippet**, không phải production-ready error handler. Nếu account bị locked giữa lúc password provider trả success và lúc lưu session, cần failure cleanup/consistency policy để không cấp một session truy cập trái trạng thái. Success handler custom cũng phải giữ session fixation protection/saved-request semantics nếu ứng dụng cần.

Không lấy epoch từ request body/client cookie. Epoch được gắn bởi server sau khi xác minh. Khi role/tenant thay đổi, `authzVersion` và authorization service có thể phải kiểm thêm; **epoch bằng nhau không chứng minh user có quyền đọc một resource cụ thể**.

## 13. Test login thật bằng MockMvc, không dùng mock principal

Các test của Spring Security Servlet có thể chạy với:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class LifecycleSecurityIntegrationTests {
    @Autowired MockMvc mvc;
    // test methods
}
~~~

Trong `@AutoConfigureMockMvc`, không đặt `addFilters=false` nếu mục tiêu là kiểm security filters. Nếu dùng `MockMvcBuilders.webAppContextSetup(context)` thủ công thì tích hợp `springSecurity()`.

Tạo hai phiên thật:

~~~java
MvcResult first = mvc.perform(
        formLogin().user("alice").password("OldDemo#123"))
    .andExpect(authenticated().withUsername("alice"))
    .andReturn();

MvcResult second = mvc.perform(
        formLogin().user("alice").password("OldDemo#123"))
    .andExpect(authenticated().withUsername("alice"))
    .andReturn();

MockHttpSession a =
        (MockHttpSession) first.getRequest().getSession(false);
MockHttpSession b =
        (MockHttpSession) second.getRequest().getSession(false);

assertNotNull(a);
assertNotNull(b);
assertNotEquals(a.getId(), b.getId());

mvc.perform(get("/me").session(a))
    .andExpect(status().isOk());
mvc.perform(get("/me").session(b))
    .andExpect(status().isOk());
~~~

Đây là **test snippet** trong class đã import `MvcResult`, `MockHttpSession`, JUnit assertions, static `formLogin`/`authenticated`/`get`/`status`, cùng app form-login/user fixtures đã cấu hình. Nó không thể chạy độc lập nếu không có security chain/controller tương ứng.

**`@WithMockUser`/`user()` không thay thế được `formLogin()`** ở đây: chúng đưa sẵn principal vào request để kiểm authorization, không test PasswordEncoder, account locked/disabled, session creation hay login failures thật.

Với REST API dùng JSON authentication filter thay vì Spring form-login, hãy gửi JSON qua filter/provider thực; không thêm `formLogin` vào app chỉ để tiện test.

## 14. Bài test khóa account

Trình tự:

1. Login Alice trên browser A/B và Bob trên C; xác nhận cả ba được GET `/me`.
2. Admin gọi lock hoặc test fixture dùng **lifecycle service thật**; xác nhận transaction commit account locked và epoch tăng.
3. Login Alice bằng password đúng lần nữa; phải bị từ chối.
4. Gửi lại session A và B; protected resource phải bị từ chối sau commit trong SLA.
5. Bob C phải tiếp tục được phép.
6. Unlock Alice; A/B **vẫn** bị từ chối vì issued epoch cũ.
7. Login Alice mới tạo D và D hoạt động bình thường.

Một assertion login mới:

~~~java
mvc.perform(formLogin()
        .user("alice").password("OldDemo#123"))
    .andExpect(unauthenticated());
~~~

Response cụ thể của endpoint form login có thể là redirect thay vì 401; đừng mặc định mọi login failure trả JSON. Test cần kiểm both authentication result and applicable client response.

**Lưu ý MockMvc:** nếu epoch guard đã gọi `MockHttpSession.invalidate()`, tái sử dụng cùng object session trong một `mvc.perform(...).session(old)` khác có thể ném `IllegalStateException`. Để kiểm **HTTP cookie replay** chính xác, dùng một integration test với Spring Session repository và cookie jar gửi lại raw cookie ID cũ, không suy status từ hành vi object mock đã invalidated.

## 15. Bài test đổi mật khẩu

Sau unlock, login D với mật khẩu cũ:

~~~text
Alice: status ACTIVE, epoch=9
Session D: issuedEpoch=9

POST /account/password:
  currentPassword = OldDemo#123
  newPassword     = NewDemo#456
  -> passwordEncoder.matches(current, oldHash) = true
  -> password hash updated
  -> epoch=10 committed
  -> D (và A/B cũ) revoked

POST /login old password -> fail
POST /login new password -> success, new session E
~~~

Assertion phải gồm:

- Mật khẩu cũ đúng mới đổi được; sai current password **không** đổi hash/epoch.
- Mật khẩu mới đạt policy; khi không đạt thì không có side effect.
- Hash trước/sau khác và hash mới không bằng plaintext password.
- `passwordEncoder.matches("NewDemo#456", storedHash)` trả true.
- Tất cả sessions đã được cấp trước thay đổi bị deny.
- Login mới bằng old password fail; bằng new password success.
- Người dùng khác vẫn login và truy cập bình thường.
- Chỉ user sở hữu account hoặc admin được phân quyền mới có thể thực hiện.
- Request thiếu CSRF/recent step-up (nếu required) bị từ chối.

Không chỉ assert endpoint `/account/password` trả `200`. Sau update phải thử **mật khẩu cũ** và **cookie cũ** như một attacker có thể làm.

## 16. Bài test logout current và logout all

**Logout current E:**

~~~text
Alice sessions E & F active
Bob session C active

POST /logout with E + valid CSRF token
  -> E invalidated
  -> F still active
  -> C still active
~~~

Spring Security test có `SecurityMockMvcRequestBuilders.logout()` nếu dùng logout filter mặc định. Cần kiểm invalidation phía server, không chỉ status/redirect của logout handler.

**Logout all Alice:**

~~~text
Alice F active
Bob C active

POST /sessions/logout-all as Alice with recent assurance
  -> bump Alice securityEpoch
  -> revoke/delete all indexed Alice sessions
  -> replay F -> deny
  -> C -> still allow
~~~

Logout all có thể invalidate cả session đang gọi. Với self-service API, lấy subject từ authenticated principal, không chấp nhận `userId` do client tự khai. Nên kiểm thử cùng user thực hiện hai logout-all requests/race để bảo đảm idempotency và không hồi sinh sessions.

## 17. Chương trình Java 17 độc lập: kiểm chứng đầy đủ các trạng thái

Chương trình sau chạy bằng **JDK 17 Standard Library**, không dùng Spring. Nó mô phỏng account store và session registry với synchronized operations để thấy rõ policy **epoch + status**. Password được lưu dưới dạng **PBKDF2WithHmacSHA256** cùng random salt để tránh ví dụ lưu plaintext; đây vẫn là **demo**, không phải `PasswordEncoder` production replacement.

Lưu tên `AccountLifecycleMultiSessionDemo.java`:

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class AccountLifecycleMultiSessionDemo {
    private static final SecureRandom RNG = new SecureRandom();

    private static byte[] derive(char[] password, byte[] salt) {
        PBEKeySpec spec = new PBEKeySpec(
                password, salt, 120_000, 256);
        try {
            return SecretKeyFactory
                    .getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("KDF unavailable", e);
        } finally {
            spec.clearPassword();
        }
    }

    private static final class Account {
        final String id;
        byte[] salt;
        byte[] verifier;
        boolean locked;
        long epoch = 1L;

        Account(String id, char[] password) {
            this.id = id;
            updatePassword(password);
        }

        boolean matches(char[] password) {
            return MessageDigest.isEqual(
                    verifier, derive(password, salt));
        }

        void updatePassword(char[] password) {
            byte[] newSalt = new byte[16];
            RNG.nextBytes(newSalt);
            byte[] newVerifier = derive(password, newSalt);
            salt = newSalt;
            verifier = newVerifier;
        }
    }

    private record Ticket(String userId, long epoch) {}

    private static final class Registry {
        private final Map<String, Account> accounts = new HashMap<>();
        private final Map<String, Ticket> sessions = new HashMap<>();
        private long counter;

        synchronized void add(String user, char[] password) {
            accounts.put(user, new Account(user, password));
        }

        synchronized String login(String user, char[] password) {
            Account a = accounts.get(user);
            if (a == null || a.locked || !a.matches(password)) {
                return null;
            }
            String id = "sid-" + (++counter);
            sessions.put(id, new Ticket(user, a.epoch));
            return id;
        }

        synchronized boolean allowed(String sessionId) {
            Ticket ticket = sessions.get(sessionId);
            if (ticket == null) {
                return false;
            }
            Account a = accounts.get(ticket.userId());
            return a != null && !a.locked
                    && ticket.epoch() == a.epoch;
        }

        synchronized void lock(String user) {
            Account a = Objects.requireNonNull(accounts.get(user));
            a.locked = true;
            a.epoch++;
        }

        synchronized void unlock(String user) {
            Account a = Objects.requireNonNull(accounts.get(user));
            a.locked = false;
            a.epoch++;
        }

        synchronized boolean changePassword(
                String user, char[] current, char[] next) {
            Account a = accounts.get(user);
            if (a == null || a.locked || !a.matches(current)) {
                return false;
            }
            a.updatePassword(next);
            a.epoch++;
            return true;
        }

        synchronized void logoutOne(String sid) {
            sessions.remove(sid);
        }

        synchronized void logoutAll(String user) {
            Account a = Objects.requireNonNull(accounts.get(user));
            a.epoch++;
            sessions.entrySet().removeIf(
                    e -> user.equals(e.getValue().userId()));
        }
    }

    public static void main(String[] args) {
        Registry r = new Registry();
        r.add("alice", "OldDemo#123".toCharArray());
        r.add("bob", "BobDemo#789".toCharArray());

        String a = r.login("alice", "OldDemo#123".toCharArray());
        String b = r.login("alice", "OldDemo#123".toCharArray());
        String c = r.login("bob", "BobDemo#789".toCharArray());

        System.out.println("start: A=" + r.allowed(a)
                + ", B=" + r.allowed(b)
                + ", Bob=" + r.allowed(c));

        r.lock("alice");
        System.out.println("locked: A=" + r.allowed(a)
                + ", B=" + r.allowed(b));
        System.out.println("login while locked: " +
                (r.login("alice", "OldDemo#123".toCharArray()) != null));

        r.unlock("alice");
        System.out.println("old session after unlock: "
                + r.allowed(a));
        String d = r.login("alice", "OldDemo#123".toCharArray());
        System.out.println("fresh login after unlock: "
                + r.allowed(d));

        System.out.println("change password: "
                + r.changePassword(
                    "alice",
                    "OldDemo#123".toCharArray(),
                    "NewDemo#456".toCharArray()));
        System.out.println("session D after change: "
                + r.allowed(d));
        System.out.println("old password login: " +
                (r.login("alice", "OldDemo#123".toCharArray()) != null));

        String e = r.login("alice", "NewDemo#456".toCharArray());
        String f = r.login("alice", "NewDemo#456".toCharArray());
        System.out.println("new password login: " + r.allowed(e));

        r.logoutOne(e);
        System.out.println("logout one: E=" + r.allowed(e)
                + ", F=" + r.allowed(f));

        r.logoutAll("alice");
        System.out.println("logout all: F=" + r.allowed(f));
        System.out.println("bob unaffected: " + r.allowed(c));
    }
}
~~~

Chạy:

~~~bash
javac AccountLifecycleMultiSessionDemo.java
java AccountLifecycleMultiSessionDemo
~~~

**Stdout chính xác:**

~~~text
start: A=true, B=true, Bob=true
locked: A=false, B=false
login while locked: false
old session after unlock: false
fresh login after unlock: true
change password: true
session D after change: false
old password login: false
new password login: true
logout one: E=false, F=true
logout all: F=false
bob unaffected: true
~~~

Diễn giải:

- A/B còn active trước lock, cùng bị deny sau lock.
- Login khi locked thất bại dù password đúng.
- Unlock không làm A/B sống lại; phải tạo session D mới.
- Password change đổi verifier và bump epoch, làm D cũ bị từ chối.
- Old password không login được, new password tạo E/F.
- Logout current E không ảnh hưởng F; logout all thu hồi F nhưng Bob C vẫn active.

**Giới hạn:** toàn bộ trạng thái trong **một JVM**, không phải HTTP cookies, Spring Security FilterChain, Redis, JWT, IdP hay transaction DB. Chương trình minh họa logic; cần integration tests trên hệ thống thật trước khi kết luận multi-device revoke hoạt động. Password cost/algorithm/rotation trong production nên dùng Spring `PasswordEncoder` theo chính sách, không dùng constant password demo.

## 18. Test multi-node và concurrency

Chạy Node 1 và Node 2 với shared account DB và Spring Session Redis/JDBC:

~~~text
Browser A --> Node 1 --+
                        +--> shared account status/epoch
Browser B --> Node 2 --+--> shared session store
Bob C      --> Node 2

Admin lock at Node 1
  -> commit locked=true, epoch=12
  -> replay A at Node 1: DENY
  -> replay B at Node 2: DENY
  -> C remains ALLOW
~~~

Một test local MockMvc **không chứng minh cross-node revoke**. Dùng hai server instances và hai cookie jars, gửi requests sau commit, đo latency từ thay đổi tới lúc tất cả paths từ chối.

Các race conditions quan trọng:

- Login B chạy đồng thời lock: không được cấp một session với epoch cũ mà còn được chấp nhận sau commit.
- Password change và login mới chạy đồng thời: verifier/epoch phải cập nhật atomic.
- Logout all quét sessions khi một session vừa tạo: epoch gate chặn những session cũ hoặc phát sai version.
- Queue/Redis cleanup tạm lỗi: outbox retry, nhưng đường kiểm status cần đáp ứng SLA.
- Unlock sau lock: tuyệt đối không giảm epoch khiến cookies cũ hồi sinh.
- Request high-risk đã authorized trước lock, nhưng commit sau lock: service cần kiểm epoch gần transaction commit theo policy.

Dùng `CountDownLatch`/barriers để tái hiện race có kiểm soát trong integration tests, không dùng `Thread.sleep` để đoán request ordering.

## 19. Refresh token, access JWT và phiên SSO

Một hệ thống OAuth2 có thể đã cấp:

~~~text
Alice Browser Session A  -> Spring Session
Refresh Token RT-A       -> Authorization Server
Access JWT AT-A          -> Resource Server (stateless verification)
IdP SSO Session          -> Identity Provider
Remember-Me Cookie       -> Persistent-token repository
~~~

**Lock account** phải ngăn Authorization Server cấp token mới. **Password reset nghi compromise** thường cần revoke refresh grants, family rotation state, remember-me, MFA proofs và sessions. Nhưng **revoke refresh token không tự làm JWT access token đã phát hành mất hiệu lực**.

Với JWT, chọn chiến lược rõ:

- TTL ngắn và chấp nhận độ trễ đến `exp`.
- Per-user epoch/security version được Resource Server tra ở request path.
- `jti` denylist cho token cụ thể.
- Opaque token/introspection với cache TTL/invalidation phù hợp.
- Gateway/central enforcement được bảo vệ khỏi đường bypass.

Một JWT chưa hết hạn có chữ ký hợp lệ **không chứng minh** account hiện vẫn active. Cũng không nên dùng ID Token OIDC làm API access token.

**SSO:** logout local Relying Party không tự logout IdP. Muốn “mọi thiết bị và mọi ứng dụng”, cần contract OIDC RP-initiated/back-channel logout hoặc deprovision enforcement cho từng RP. API key/service token có thể thuộc lifecycle độc lập; xử lý theo policy owner/tenant.

## 20. Những test negative dễ bị bỏ sót

| Trường hợp | Assertion |
|---|---|
| Anonymous gọi đổi password | Deny, không cập nhật hash. |
| Alice gửi userId của Bob để đổi password | Deny, không ảnh hưởng Bob. |
| Đổi password với old password sai | Hash/epoch giữ nguyên, không revoke không chủ ý. |
| Đổi new password không đạt policy | Từ chối trước commit. |
| POST đổi password thiếu CSRF | `403` khi dùng cookie session/CSRF policy. |
| User bị locked cố login | Authentication bị từ chối dù password đúng. |
| Cookie A replay sau lock | Deny. |
| Cookie A replay sau unlock | Vẫn deny (không revive). |
| Cookie D replay sau password change | Deny. |
| Logout E nhưng F vẫn còn | F thành công theo logout current semantics. |
| Logout all Alice | Mọi Alice sessions deny, Bob không bị đụng. |
| Remove physically session nhưng browser có bản cookie cũ | Không khôi phục authenticated context. |
| `SessionRegistry.expireNow()` | Kiểm filter xử lý ở request tiếp theo/cross-node. |
| JWT cũ sau lock | Theo epoch/denylist/TTL SLA đã định, không mặc định revoke. |
| Retry hai lần logout all | Không phát sinh cấp quyền hoặc restore session. |
| Node 2 cache stale sau lock | High-risk API deny trong SLA. |
| Cleanup queue down | State gate vẫn deny; event retry/reconciliation. |
| Admin không có quyền lock user khác tenant | Forbidden, không có side effect. |
| Account login qua OIDC, password local không tồn tại | Không dùng local password change workflow sai kiến trúc. |
| Log/audit/metrics | Không lưu cookie, OTP, password, raw JWT hoặc session ID. |

Với POST cần phân biệt `403` do thiếu CSRF và `403` do thiếu role: khi muốn test authorization, cung cấp CSRF hợp lệ; khi test CSRF, assert missing/invalid token riêng.

## 21. Kế hoạch kiểm thử tổng hợp trong CI

1. **Unit test state machine:** lock/unlock, epoch monotonic, password change preconditions, logout current/all idempotency.
2. **Servlet security integration:** `@SpringBootTest` + `@AutoConfigureMockMvc`; form login thật, sessions A/B/C, negative paths.
3. **Persistence integration:** DB transaction, account row locking, outbox commit/retry và expected hash/state.
4. **Shared session integration:** Spring Session Redis/JDBC principal index, cookie replay sau `deleteById`.
5. **Multi-node:** Node 1/2 với cùng account/session state, load-balancer routing, cache invalidation.
6. **OAuth/IdP contracts:** refresh revoke, stale JWT, OIDC local RP session, remember-me/MFA proof nếu có.
7. **Concurrency/TOCTOU:** kiểm request start trước lock nhưng commit sau lock, no high-risk side effect.
8. **Operational/privacy:** audit without secrets, metrics theo revoke SLA, chaos test queue/store outage.

**Điều kiện nghiệm thu:** có bằng chứng HTTP/protected resource từ **session cũ** không còn được phép sau lock/change/logout all; mọi phiên của Bob không bị ảnh hưởng; đăng nhập mới obey status/password. Một test chỉ assert DB flag đúng hoặc response mutation API trả 200 **không đủ**.

## 22. Audit, metrics và bảo vệ thông tin nhạy cảm

Một audit event chuẩn hóa có thể có:

~~~json
{
  "eventId": "evt-901",
  "eventType": "ACCOUNT_LOCKED",
  "actorUserId": "security-admin",
  "subjectUserId": "usr-1001",
  "securityEpoch": 7,
  "occurredAt": "2026-11-06T09:00:00Z",
  "correlationId": "req-8fa",
  "cleanupState": "PENDING"
}
~~~

Đây là schema **do ứng dụng định nghĩa**, không phải Spring Security tự tạo. `cleanupState` phải dựa trên xác nhận từ cleanup services. Không log raw password/new password, password hash, bearer/refresh token, session cookie, raw OTP/recovery code, Authorization header hay entire SecurityContext.

Metrics gợi ý:

~~~text
account_lock_total
account_unlock_total
password_change_success_total
password_change_failure_total
logout_current_total
logout_all_total
stale_session_rejected_total
session_revocation_success_total
session_revocation_lag_seconds
session_reconciliation_discrepancy_total
~~~

Không đặt user ID/session ID/email/token thành metric labels có cardinality cao. Có thể lưu subject/actor trong audit store có quyền truy cập, retention và mã hóa phù hợp.

**SLA revoke phải đo từ account-update commit đến lúc request cũ bị từ chối tại resource thật**, không phải đo đến lúc cleanup event được enqueue.

## 23. Sai lầm phổ biến và cách khắc phục

**Sai lầm 1: chỉ set account.locked=true.** Session cũ có thể giữ `SecurityContext`. Hãy test replay A/B và dùng gate/cleanup.

**Sai lầm 2: chỉ update password hash.** Cookie cũ, remember-me và refresh grants không tự bị revoke. Hãy xây event/epoch policy theo credential scope.

**Sai lầm 3: dùng `SecurityContextHolder.clearContext()` cho logout all.** Chỉ clear context hiện tại. Dùng shared session index và/hoặc epoch guard.

**Sai lầm 4: tin `SessionRegistry.expireNow()` xóa ngay mọi HttpSession.** Đây có thể chỉ là expired marker, cần filter và cross-node strategy.

**Sai lầm 5: quên principal index.** `findByPrincipalName` rỗng nếu giá trị index không được populate hoặc dùng username khác. Test index bằng hai sessions thật.

**Sai lầm 6: unlock làm sessions cũ sống lại.** Không giảm epoch, không chỉ kiểm flag locked.

**Sai lầm 7: test bằng `@WithMockUser`.** Nó bỏ qua login/provider, không có hai browser sessions thực. Dùng form/basic/custom filter thật.

**Sai lầm 8: dùng một `MockHttpSession` đã invalidate rồi kỳ vọng status 401.** Có thể throw từ mock; dùng HTTP cookie replay test với server/session store thật.

**Sai lầm 9: logout all quét nhầm Bob.** Ánh xạ theo stable internal user ID, tenant boundary rõ, test cô lập.

**Sai lầm 10: coi JWT signature hợp lệ là account còn active.** Cần TTL/epoch/denylist/introspection theo SLA.

**Sai lầm 11: dùng event async như chặn truy cập duy nhất.** Event lag tạo cửa sổ rủi ro; dùng authoritative state gate.

**Sai lầm 12: bắt đầu request trước lock rồi vẫn commit nghiệp vụ nhạy cảm sau lock.** Recheck tại transaction/business boundary.

**Sai lầm 13: tắt CSRF để POST logout/password change xanh test.** Bảo vệ endpoint thay đổi trạng thái và tách role vs CSRF tests.

**Sai lầm 14: log full Authentication hoặc raw session ID để debug.** Có thể tạo session hijacking; dùng correlation ID và redacted metadata.

## 24. Checklist trước khi đưa chức năng vào production

- [ ] Policy nói rõ lock chỉ chặn login mới hay mọi session hiện hữu.
- [ ] Login manager/provider kiểm `isAccountNonLocked`/`isEnabled` theo trạng thái thật.
- [ ] Account security epoch là monotonic, được commit trước khi công bố revoke thành công.
- [ ] Mọi request session-backed nhạy cảm kiểm current account status/epoch hoặc session server-side đã bị delete.
- [ ] Unlock không revive phiên hoặc token epoch cũ.
- [ ] Password change xác minh old credential, new password policy, CSRF/reauth/MFA nếu cần.
- [ ] Password hash được quản lý bằng `PasswordEncoder` thích hợp.
- [ ] Thay password bump epoch, xử lý current/other sessions và grants theo policy.
- [ ] Logout current hủy server-side session chứ không chỉ xóa browser cookie.
- [ ] Logout all hoạt động cross-node, có principal index/epoch gate và không ảnh hưởng user khác.
- [ ] Spring Session index theo principal có contract ổn định; multi-node tests thực.
- [ ] Nếu dùng SessionRegistry expireNow, xác nhận filter/registry trên các nodes.
- [ ] JWT access, refresh token, remember-me, API key, MFA proof và SSO được quản lý riêng nếu tồn tại.
- [ ] Request concurrency/cache staleness và TOCTOU được test/giới hạn.
- [ ] Outbox/retry/reconciliation có audit/revoke SLA rõ ràng.
- [ ] Không có sensitive credentials trong logs, metrics hoặc notifications.
- [ ] Negative tests chạy trong CI cùng các test positive.
- [ ] Có runbook emergency lock, reset, logout all, unlock và security notifications.

## 25. Tổng kết

**Khóa tài khoản, đổi mật khẩu và đăng xuất nhiều phiên là ba hành động có cùng một nguyên tắc: bằng chứng xác thực cũ phải mất hiệu lực đúng phạm vi và thời điểm cam kết.** Trong Spring Security, `UserDetails` flags giúp chặn login mới nhưng không tự làm mọi `SecurityContext` đã lưu trong HttpSession bị hủy. Password hash mới cũng không tự thu hồi bearer JWT/refresh grants.

Một thiết kế đáng tin là:

**Commit account state/password hash + bump security epoch → enforce ở request path → cleanup sessions/tokens bằng shared repositories → audit/reconciliation → kiểm thử replay trên nhiều thiết bị và nodes.**

Nếu một system test chứng minh A/B bị chặn sau lock hoặc password change, E bị chặn sau logout current nhưng F vẫn hoạt động, F bị chặn sau logout all còn Bob C không bị ảnh hưởng, hệ thống mới có bằng chứng đúng phạm vi chức năng.

## Tài liệu tham khảo

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextRepository`, concurrent sessions và `SessionRegistry`.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): session invalidation, logout handlers và CSRF.
- [Spring Security — UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html): account status checks và DaoAuthenticationProvider.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): Servlet security test filter chain.
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): formLogin/user mock semantics.
- [Spring Session — API](https://docs.spring.io/spring-session/reference/api.html): `FindByIndexNameSessionRepository` và principal index.
- [Spring Session — Redis Guide](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): shared sessions across instances.
- [RFC 7009 — OAuth2 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): revocation of OAuth grants/tokens.
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): opaque token active state.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifecycle, revocation và security events.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): password change và account management.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): recovery và invalidating existing sessions.
